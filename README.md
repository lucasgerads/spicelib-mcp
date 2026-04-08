# spicelib-mcp

A thin MCP server that wraps [ngspice](https://ngspice.sourceforge.io/) for circuit simulation. The heavy lifting — simulator invocation, `.raw` file parsing, and multi-simulator abstraction — is done by [spicelib](https://github.com/nunobrum/spicelib), which deserves most of the credit. This project is purely a transport layer that exposes spicelib's functionality as MCP tools for use with Claude Code.

Primary use case: behavioral model fitting — run simulations, compare against real measurements, iterate on SPICE models.

## Tools

- `run_ac_analysis` — AC frequency sweep, returns magnitude/phase data
- `run_transient` — transient simulation, returns time-domain waveforms
- `run_dc_op` — DC operating point analysis

Results are saved as `.npz` files alongside the netlist for further analysis and plotting.

## Requirements

- Python 3.10+
- ngspice installed on PATH (`sudo apt install ngspice`)

## License

GPL-3.0-or-later
