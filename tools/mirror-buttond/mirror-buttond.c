// SPDX-License-Identifier: GPL-2.0
/*
 * mirror-buttond: turn the Mirror's bottom button (SNVS ONOFF pad, seen by
 * Linux as KEY_PROG1 from the snvs_pwrkey driver) into generic events for apps.
 *
 * Clients connect to a local stream socket and read newline-terminated events:
 *   press    button went down (immediate)
 *   release  button went up (immediate)
 *   tap      one short press (sent after the double-tap window)
 *   double   two short presses
 *   hold     still down after the hold time (sent while held)
 *
 * Sleeps in poll() between events. Slow clients miss events; they never block
 * the daemon. Usage: mirror-buttond [-s socket] [-H hold_ms] [-d double_ms]
 *                                   [-i input_device]
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define BUTTON_PHYS	"snvs-pwrkey/input0"
#define BUTTON_KEY	KEY_PROG1
#define MAX_CLIENTS	16

enum state {
	IDLE,		/* nothing in progress */
	FIRST_DOWN,	/* first press, hold timer running */
	WAIT_SECOND,	/* first press released, double-tap timer running */
	SECOND_DOWN,	/* second press, hold timer running */
	HELD,		/* hold already sent, waiting for release */
};

static int clients[MAX_CLIENTS];
static int nclients;

static long long now_ms(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

static void emit(const char *event)
{
	char line[16];
	int len = snprintf(line, sizeof(line), "%s\n", event);
	int i = 0;

	while (i < nclients) {
		ssize_t n = send(clients[i], line, len,
				 MSG_DONTWAIT | MSG_NOSIGNAL);

		if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
			close(clients[i]);
			clients[i] = clients[--nclients];
			continue;
		}
		i++;
	}
}

/* event numbers change between boots, so find the button by its phys string */
static int open_button(void)
{
	DIR *dir = opendir("/dev/input");
	struct dirent *de;
	int fd = -1;

	if (!dir)
		return -1;

	while (fd < 0 && (de = readdir(dir))) {
		char path[300], phys[64] = "";
		int f;

		if (strncmp(de->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "/dev/input/%s", de->d_name);
		f = open(path, O_RDONLY | O_CLOEXEC);
		if (f < 0)
			continue;
		if (ioctl(f, EVIOCGPHYS(sizeof(phys) - 1), phys) >= 0 &&
		    !strcmp(phys, BUTTON_PHYS))
			fd = f;
		else
			close(f);
	}
	closedir(dir);
	return fd;
}

static int listen_socket(const char *path)
{
	struct sockaddr_un addr = { .sun_family = AF_UNIX };
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);

	if (fd < 0 || strlen(path) >= sizeof(addr.sun_path))
		return -1;
	strcpy(addr.sun_path, path);
	unlink(path);
	if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
	    chmod(path, 0660) < 0 || listen(fd, MAX_CLIENTS) < 0)
		return -1;
	return fd;
}

int main(int argc, char **argv)
{
	const char *sock_path = "/run/mirror-button/events.sock";
	const char *input_path = NULL;
	int hold_ms = 2000, double_ms = 350;
	enum state state = IDLE;
	long long deadline = -1;
	int button, listener, opt;

	while ((opt = getopt(argc, argv, "s:H:d:i:")) != -1) {
		switch (opt) {
		case 's': sock_path = optarg; break;
		case 'H': hold_ms = atoi(optarg); break;
		case 'd': double_ms = atoi(optarg); break;
		case 'i': input_path = optarg; break;
		default:
			fprintf(stderr, "usage: %s [-s socket] [-H hold_ms] [-d double_ms] [-i input]\n",
				argv[0]);
			return 2;
		}
	}

	signal(SIGPIPE, SIG_IGN);

	button = input_path ? open(input_path, O_RDONLY | O_CLOEXEC) : open_button();
	if (button < 0) {
		fprintf(stderr, "mirror-buttond: button input device not found\n");
		return 1;
	}
	listener = listen_socket(sock_path);
	if (listener < 0) {
		fprintf(stderr, "mirror-buttond: cannot listen on %s: %s\n",
			sock_path, strerror(errno));
		return 1;
	}

	for (;;) {
		struct pollfd fds[2] = {
			{ .fd = button, .events = POLLIN },
			{ .fd = listener, .events = POLLIN },
		};
		int timeout = -1;

		if (deadline >= 0) {
			long long left = deadline - now_ms();

			timeout = left > 0 ? (int)left : 0;
		}

		if (poll(fds, 2, timeout) < 0) {
			if (errno == EINTR)
				continue;
			return 1;
		}

		if (fds[1].revents & POLLIN) {
			int c = accept4(listener, NULL, NULL, SOCK_CLOEXEC);

			if (c >= 0) {
				if (nclients < MAX_CLIENTS)
					clients[nclients++] = c;
				else
					close(c);
			}
		}

		if (fds[0].revents & POLLIN) {
			struct input_event ev;
			ssize_t n = read(button, &ev, sizeof(ev));

			/* the device went away: exit and let systemd restart us */
			if (n != sizeof(ev)) {
				fprintf(stderr, "mirror-buttond: input device lost\n");
				return 1;
			}
			if (ev.type == EV_KEY && ev.code == BUTTON_KEY && ev.value == 1) {
				emit("press");
				if (state == IDLE)
					state = FIRST_DOWN;
				else if (state == WAIT_SECOND)
					state = SECOND_DOWN;
				deadline = now_ms() + hold_ms;
			} else if (ev.type == EV_KEY && ev.code == BUTTON_KEY && ev.value == 0) {
				emit("release");
				if (state == FIRST_DOWN) {
					state = WAIT_SECOND;
					deadline = now_ms() + double_ms;
				} else {
					if (state == SECOND_DOWN)
						emit("double");
					state = IDLE;
					deadline = -1;
				}
			}
		}

		if (deadline >= 0 && now_ms() >= deadline) {
			deadline = -1;
			if (state == WAIT_SECOND) {
				emit("tap");
				state = IDLE;
			} else if (state == FIRST_DOWN || state == SECOND_DOWN) {
				emit("hold");
				state = HELD;
			}
		}
	}
}
