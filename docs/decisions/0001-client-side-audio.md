# 0001. All sound is generated in the browser; the site is static

- Status: Accepted (owner, 2026-10-26)
- Date: 2026-10-25

## Context

The app has to make sound live while the user turns knobs, and it should eventually be a public
web page that can be hosted cheaply. The DSP is light: a few hundred floating-point operations
per sample per box.

## Decision

All synthesis runs on the user's machine, inside the browser. The real-time path is an
AudioWorklet, the browser's dedicated audio thread. WAV export renders offline in a Web Worker.
The deployed site is static files only (HTML/JS/WASM/JSON), with no application server.

## Consequences

- Zero server cost and no audio latency from the network. It can be hosted on GitHub Pages,
  Cloudflare Pages, Netlify or the owner's own server.
- AudioWorklet needs a secure context (HTTPS or `localhost`), which all of those hosts provide.
  It is supported by every current major browser.
- The real-time engine must be written in a language that runs in the browser: JavaScript or
  TypeScript, or something compiled to WebAssembly (see ADR 0002). Python cannot be the
  real-time engine.
- Features that need a server (accounts, sharing patches online, a gallery) would be added
  later as small optional services, without changing the audio path.

## Alternatives considered

- **Python server that streams audio** (FastAPI + WebSocket). Rejected: it adds latency to
  every knob move, costs CPU on a server for every listener, and is complex to scale.
- **Pyodide** (CPython compiled to WebAssembly). Rejected for the real-time path: it is a large
  download (around 10 MB or more), starts slowly, has garbage-collection pauses, and is
  impractical inside the audio thread. It could still power a future "write your own ODE in
  Python" feature that runs offline.
