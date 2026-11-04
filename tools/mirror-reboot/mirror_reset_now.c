// SPDX-License-Identifier: GPL-2.0
/*
 * Reset or power off the board now, through the firmware's PSCI call, as soon as
 * this module loads. Loaded only by the system-shutdown hook, at the very end of
 * a shutdown: the kernel's own path gets stuck before it reaches the firmware.
 */
#include <linux/arm-smccc.h>
#include <linux/module.h>
#include <uapi/linux/psci.h>

static bool off;
module_param(off, bool, 0444);
MODULE_PARM_DESC(off, "Power off instead of resetting");

static int __init mirror_reset_now_init(void)
{
	struct arm_smccc_res res;

	arm_smccc_smc(off ? PSCI_0_2_FN_SYSTEM_OFF : PSCI_0_2_FN_SYSTEM_RESET,
		      0, 0, 0, 0, 0, 0, 0, &res);
	return -EIO;
}
module_init(mirror_reset_now_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Immediate PSCI reset or power-off, for the shutdown hook");
