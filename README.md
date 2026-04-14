# spicelib-mcp

A thin MCP server that wraps [spicelib](https://github.com/nunobrum/spicelib) for circuit simulation. The heavy lifting — simulator invocation, `.raw` file parsing, and multi-simulator abstraction — is done by spicelib, which deserves most of the credit. This project is purely a transport layer that exposes spicelib's functionality as MCP tools for use with Claude Code (and other coding agents).

Primary use case: behavioral model fitting — run simulations, compare against real measurements, iterate on SPICE models.

## Tools

- `run_ac_analysis` — AC frequency sweep, returns magnitude/phase data
- `run_transient` — transient simulation, returns time-domain waveforms
- `run_dc_op` — DC operating point analysis
- `run_sweep` — run multiple simulations in parallel, sweeping component values

Results are saved as `.npz` files alongside the netlist for further analysis and plotting.

## Supported simulators

| Simulator | `SPICE_SIMULATOR` value | Install |
|---|---|---|
| [ngspice](https://ngspice.sourceforge.io/) | `ngspice` (default) | `sudo apt install ngspice` |
| [LTspice](https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html) | `ltspice` | Download from Analog Devices |
| [Qspice](https://www.qorvo.com/design-hub/design-tools/interactive/qspice) | `qspice` | Download from Qorvo |

Set the `SPICE_PATH` environment variable to override the simulator binary location.

## Requirements

- Python 3.10+
- A supported simulator installed and on PATH

## License

GPL-3.0-or-later
