"""
spicelib MCP server — wraps ngspice for use with Claude Code.

HTTP entry point (for mcp dev inspector):
    python server.py

Stdio entry point (for Claude Code):
    python server_stdio.py
"""

import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Suppress spicelib's "No instruction matching pattern" warnings — these are
# expected when we remove analysis commands that aren't present in the netlist.
logging.getLogger("spicelib").setLevel(logging.CRITICAL)

import numpy as np
from mcp.server.fastmcp import FastMCP
from spicelib.editor.spice_editor import SpiceEditor
from spicelib.raw.raw_read import RawRead
from spicelib.simulators.ngspice_simulator import NGspiceSimulator
from spicelib.simulators.ltspice_simulator import LTspice
from spicelib.simulators.qspice_simulator import Qspice
from spicelib.sim.sim_runner import SimRunner
import kicad_compat

mcp = FastMCP("spicelib")

_SIMULATOR_MAP = {
    "ngspice": NGspiceSimulator,
    "ltspice": LTspice,
    "qspice":  Qspice,
}
_sim_name = os.environ.get("SPICE_SIMULATOR", "ngspice").lower()
Simulator = _SIMULATOR_MAP.get(_sim_name)
if Simulator is None:
    print(f"WARNING: Unknown SPICE_SIMULATOR '{_sim_name}'. Valid options: {list(_SIMULATOR_MAP)}. Falling back to ngspice.",
          file=sys.stderr, flush=True)
    Simulator = NGspiceSimulator

_SPICE_PATH = os.environ.get("SPICE_PATH")
if _SPICE_PATH:
    Simulator.spice_exe = [_SPICE_PATH]

if not Simulator.is_available():
    print(f"WARNING: {_sim_name} not found on PATH. Set SPICE_PATH env var to override.",
          file=sys.stderr, flush=True)


# ── analysis type patterns for removal before injection ──────────────────────
_ANALYSIS_PATTERNS = [r"\.ac\b", r"\.tran\b", r"\.op\b", r"\.dc\b"]


def _prepare_and_run(netlist_path: str, analysis_cmd: str | None = None) -> tuple[Path, Path]:
    """Copy netlist to a temp dir, optionally inject an analysis command, run ngspice.

    Returns (raw_path, tmp_dir). The caller must shutil.rmtree(tmp_dir) when done.
    """
    src = Path(netlist_path).expanduser().resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix="spicelib_mcp_"))
    tmp_net = tmp_dir / src.name
    shutil.copy2(src, tmp_net)

    tmp_net.write_text(kicad_compat.apply_all(tmp_net.read_text()))

    if analysis_cmd is not None:
        ed = SpiceEditor(tmp_net, encoding="utf-8")
        for pattern in _ANALYSIS_PATTERNS:
            ed.remove_Xinstruction(pattern)
        ed.add_instruction(analysis_cmd)
        ed.save_netlist(tmp_net)

    rc = Simulator.run(tmp_net, exe_log=True)
    raw_path = tmp_net.with_suffix(".raw")
    if not raw_path.exists():
        raise RuntimeError(f"ngspice returned code {rc} and produced no .raw file")
    return raw_path, tmp_dir


def _save_npz(out_path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Save simulation arrays to a .npz file."""
    np.savez_compressed(out_path, **{k.replace("/", "_").replace(":", "_"): v
                                     for k, v in arrays.items()})


# =============================================================================
# Tools
# =============================================================================

@mcp.tool()
def run_ac_analysis(netlist_path: str, start_freq: str, stop_freq: str,
                    points_per_decade: int = 20) -> str:
    """Run an AC frequency sweep on a SPICE netlist.

    Injects a `.ac dec <points_per_decade> <start_freq> <stop_freq>` command
    into a temporary copy of the netlist (does not modify the original).

    Results are saved to a .npz file next to the netlist. Load with:
        data = np.load('netlist_ac.npz')
        freq = data['frequency_hz']
        # traces are stored as complex values, e.g. data['v(out)']

    For sweeping a component value or parameter across multiple AC runs in
    parallel, use run_sweep(analysis_cmd=".ac dec N fstart fstop") instead.

    Args:
        netlist_path: Absolute path to the netlist file (.net, .sp, .cir, etc.)
        start_freq: Start frequency with optional SPICE suffix, e.g. "1", "1k", "100"
        stop_freq: Stop frequency, e.g. "1G", "100meg"
        points_per_decade: Points per decade (default 20)

    Returns:
        JSON summary with data_file path, frequency range, and trace names.
    """
    try:
        src = Path(netlist_path).expanduser().resolve()
        raw_path, tmp_dir = _prepare_and_run(
            netlist_path,
            f".ac dec {points_per_decade} {start_freq} {stop_freq}",
        )
        try:
            ltr = RawRead(raw_path, traces_to_read='*', verbose=False)
            freq = np.abs(ltr.get_axis())
            arrays = {"frequency_hz": freq}
            trace_names = [n for n in ltr.get_trace_names()
                           if n.lower() not in ("frequency", "freq")]
            for name in trace_names:
                arrays[name] = ltr.get_wave(name)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        out_path = src.with_name(src.stem + "_ac")
        _save_npz(out_path, arrays)
        return json.dumps({
            "type": "ac",
            "data_file": str(out_path) + ".npz",
            "frequency_range_hz": [float(freq[0]), float(freq[-1])],
            "points": len(freq),
            "traces": trace_names,
        })
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def run_transient(netlist_path: str, step_time: str, stop_time: str,
                  start_time: str = "0") -> str:
    """Run a transient simulation on a SPICE netlist.

    Injects a `.tran <step_time> <stop_time> <start_time>` command into a
    temporary copy of the netlist (does not modify the original).

    Results are saved to a .npz file next to the netlist. Load with:
        data = np.load('netlist_tran.npz')
        time = data['time_s']
        vout = data['v(out)']

    For sweeping a component value or parameter across multiple transient runs
    in parallel, use run_sweep(analysis_cmd=".tran step stop") instead.

    Args:
        netlist_path: Absolute path to the netlist file
        step_time: Time step with SPICE suffix, e.g. "1n", "10u", "1m"
        stop_time: Simulation end time, e.g. "1m", "100u"
        start_time: Time at which to start saving data (default "0")

    Returns:
        JSON summary with data_file path, time range, and trace names.
    """
    try:
        src = Path(netlist_path).expanduser().resolve()
        raw_path, tmp_dir = _prepare_and_run(
            netlist_path,
            f".tran {step_time} {stop_time} {start_time}",
        )
        try:
            ltr = RawRead(raw_path, traces_to_read='*', verbose=False)
            time = ltr.get_axis()
            arrays = {"time_s": time}
            trace_names = [n for n in ltr.get_trace_names() if n.lower() != "time"]
            for name in trace_names:
                arrays[name] = np.real(ltr.get_wave(name))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        out_path = src.with_name(src.stem + "_tran")
        _save_npz(out_path, arrays)
        return json.dumps({
            "type": "transient",
            "data_file": str(out_path) + ".npz",
            "time_range_s": [float(time[0]), float(time[-1])],
            "points": len(time),
            "traces": trace_names,
        })
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def run_dc_op(netlist_path: str) -> str:
    """Run a DC operating point analysis on a SPICE netlist.

    Injects a `.op` command into a temporary copy of the netlist (does not
    modify the original file). DC op results are small enough to return directly.

    Args:
        netlist_path: Absolute path to the netlist file

    Returns:
        JSON string with keys:
          type     — "dc_op"
          nodes    — dict of node_name → voltage (V)
          currents — dict of device_name → current (A)
    """
    try:
        raw_path, tmp_dir = _prepare_and_run(netlist_path, ".op")
        try:
            ltr = RawRead(raw_path, traces_to_read='*', verbose=False)
            nodes = {}
            currents = {}
            for name in ltr.get_trace_names():
                val = float(np.real(ltr.get_trace(name)[0]))
                if name.upper().startswith("I(") or name.upper().startswith("IX("):
                    currents[name] = val
                else:
                    nodes[name] = val
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return json.dumps({"type": "dc_op", "nodes": nodes, "currents": currents})
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def run_sweep(netlist_path: str, analysis_cmd: str, runs: list[dict],
              parallel: int = 4) -> str:
    """Run multiple SPICE simulations in parallel, sweeping component values.

    Uses spicelib's SimRunner to execute runs concurrently. Each run gets its
    own .npz file. Use this instead of calling run_ac_analysis / run_transient
    in a loop — it's significantly faster for multi-run sweeps.

    Example — sweep capacitor C1 across three values with a transient analysis:
        run_sweep(
            netlist_path="/path/to/filter.cir",
            analysis_cmd=".tran 1n 1u",
            runs=[{"C1": "1p"}, {"C1": "10p"}, {"C1": "100p"}],
        )
    Output files: filter_sweep_001.npz, filter_sweep_002.npz, filter_sweep_003.npz

    Each dict in `runs` maps component reference designators or SPICE parameter
    names to their new values (strings with optional SPICE suffix, e.g. "4.7k").

    Args:
        netlist_path: Absolute path to the netlist file
        analysis_cmd: Full SPICE analysis line, e.g. ".tran 1n 1u" or ".ac dec 20 1 1G"
        runs: List of dicts, one per simulation. Keys are component names or
              parameter names; values are the new value strings.
        parallel: Maximum number of simultaneous ngspice processes (default 4)

    Returns:
        JSON list of per-run summaries, each with keys:
          run        — 1-indexed run number
          data_file  — path to the .npz file
          values     — the component/parameter values used for this run
          traces     — list of trace names in the .npz
    """
    try:
        src = Path(netlist_path).expanduser().resolve()
        tmp_dir = Path(tempfile.mkdtemp(prefix="spicelib_mcp_sweep_"))
        try:
            # Write the kicad-fixed base netlist once; SimRunner copies from it.
            base_net = tmp_dir / src.name
            base_net.write_text(kicad_compat.apply_all(src.read_text()))

            runner = SimRunner(simulator=Simulator,
                               parallel_sims=parallel,
                               output_folder=tmp_dir,
                               verbose=False)

            for i, values in enumerate(runs, start=1):
                ed = SpiceEditor(base_net, encoding="utf-8")
                for pattern in _ANALYSIS_PATTERNS:
                    ed.remove_Xinstruction(pattern)
                ed.add_instruction(analysis_cmd)
                for ref, val in values.items():
                    ed.set_component_value(ref, val)
                runner.run(ed, run_filename=f"{src.stem}_sweep_{i:03d}.cir", exe_log=True)

            runner.wait_completion()

            cmd_lower = analysis_cmd.strip().lower()
            results = []
            for task in sorted(runner.completed_tasks, key=lambda t: t.runno):
                raw_path = task.raw_file
                runno = task.runno
                ltr = RawRead(raw_path, traces_to_read='*', verbose=False)
                axis = ltr.get_axis()
                trace_names = ltr.get_trace_names()

                # Determine axis key from analysis type
                if cmd_lower.startswith(".ac"):
                    axis_key = "frequency_hz"
                    axis_data = np.abs(axis)
                    scalar_traces = [n for n in trace_names
                                     if n.lower() not in ("frequency", "freq")]
                elif cmd_lower.startswith(".tran"):
                    axis_key = "time_s"
                    axis_data = np.real(axis)
                    scalar_traces = [n for n in trace_names if n.lower() != "time"]
                else:
                    axis_key = "axis"
                    axis_data = axis
                    scalar_traces = trace_names

                arrays = {axis_key: axis_data}
                for name in scalar_traces:
                    wave = ltr.get_wave(name)
                    arrays[name] = np.real(wave) if cmd_lower.startswith(".tran") else wave

                out_path = src.with_name(f"{src.stem}_sweep_{runno:03d}")
                _save_npz(out_path, arrays)
                results.append({
                    "run": runno,
                    "data_file": str(out_path) + ".npz",
                    "values": runs[runno - 1],
                    "traces": scalar_traces,
                })

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return json.dumps(results)
    except Exception as e:
        return f"ERROR: {e}"


if __name__ == "__main__":
    mcp.run(transport="sse")
