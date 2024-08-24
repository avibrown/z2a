#
# SymbiYosys (sby) -- Front-end for Yosys-based formal verification flows
#
# Copyright (C) 2016  Claire Xenia Wolf <claire@yosyshq.com>
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

import re, getopt
from sby_core import SbyProc
from sby_engine_aiger import aigsmt_exit_callback

def run(mode, task, engine_idx, engine):
    abc_opts, abc_command = getopt.getopt(engine[1:], "", [])

    if len(abc_command) == 0:
        task.error("Missing ABC command.")

    for o, a in abc_opts:
        task.error("Unexpected ABC engine options.")

    if abc_command[0] == "bmc3":
        if mode != "bmc":
            task.error("ABC command 'bmc3' is only valid in bmc mode.")
        abc_command[0] += f" -F {task.opt_depth} -v"

    elif abc_command[0] == "sim3":
        if mode != "bmc":
            task.error("ABC command 'sim3' is only valid in bmc mode.")
        abc_command[0] += f" -F {task.opt_depth} -v"

    elif abc_command[0] == "pdr":
        if mode != "prove":
            task.error("ABC command 'pdr' is only valid in prove mode.")
        abc_command[0] += f" -v -I engine_{engine_idx}/invariants.pla"

    else:
        task.error(f"Invalid ABC command {abc_command[0]}.")

    smtbmc_vcd = task.opt_vcd and not task.opt_vcd_sim
    run_aigsmt = smtbmc_vcd or (task.opt_append and task.opt_append_assume)
    smtbmc_append = 0
    sim_append = 0
    log = task.log_prefix(f"engine_{engine_idx}")

    if task.opt_append_assume:
        smtbmc_append = task.opt_append
    elif smtbmc_vcd:
        if not task.opt_append_assume:
            log("For VCDs generated by smtbmc the option 'append_assume off' is ignored")
        smtbmc_append = task.opt_append
    else:
        sim_append = task.opt_append

    proc = SbyProc(
        task,
        f"engine_{engine_idx}",
        task.model("aig"),
        f"""cd {task.workdir}; {task.exe_paths["abc"]} -c 'read_aiger model/design_aiger.aig; fold{
                " -s" if task.opt_aigfolds or (abc_command[0].startswith("pdr ") and "-d" in abc_command[1:]) else ""
                }; strash; {" ".join(abc_command)}; write_cex -a engine_{engine_idx}/trace.aiw'""",
        logfile=open(f"{task.workdir}/engine_{engine_idx}/logfile.txt", "w")
    )
    proc.checkretcode = True

    proc.noprintregex = re.compile(r"^\.+$")
    proc_status = None

    def output_callback(line):
        nonlocal proc_status

        match = re.match(r"^Output [0-9]+ of miter .* was asserted in frame [0-9]+.", line)
        if match: proc_status = "FAIL"

        match = re.match(r"^Simulation of [0-9]+ frames for [0-9]+ rounds with [0-9]+ restarts did not assert POs.", line)
        if match: proc_status = "UNKNOWN"

        match = re.match(r"^Stopping BMC because all 2\^[0-9]+ reachable states are visited.", line)
        if match: proc_status = "PASS"

        match = re.match(r"^No output asserted in [0-9]+ frames.", line)
        if match: proc_status = "PASS"

        match = re.match(r"^Property proved.", line)
        if match: proc_status = "PASS"

        return line

    def exit_callback(retcode):
        aigsmt_exit_callback(task, engine_idx, proc_status,
            run_aigsmt=run_aigsmt, smtbmc_vcd=smtbmc_vcd, smtbmc_append=smtbmc_append, sim_append=sim_append, )

    proc.output_callback = output_callback
    proc.register_exit_callback(exit_callback)
