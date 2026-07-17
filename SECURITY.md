# Security

Report vulnerabilities privately to xavier.grehant@gmail.com — please do not open a
public issue for anything exploitable. Of particular interest: escapes from the wasm
solver sandbox (wasmtime: fuel and memory caps, zero imports), and any path by which
solver output enters a tree as anything other than a `derived`, content-addressed
proposal.
