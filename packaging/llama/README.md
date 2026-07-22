# llama.cpp runtime

AM Configurator builds and bundles the exact llama.cpp revision recorded in
`manifest.json`. The runtime is MIT-licensed; its notice is in `MIT.txt`.

The application bundle contains `llama-cli`, `llama-server`, and no model
weights. Model files are selected by the user from local storage. The
application never downloads, copies, modifies, or deletes those files.

The official [llama.cpp advisory list](https://github.com/ggml-org/llama.cpp/security)
was checked on 2026-07-21 before this pin was promoted. Release `b9637` is newer
than every published fixed-version boundary at that time. The one published
advisory without a patched version is limited to the RPC backend, which this
manifest disables at compile time with `GGML_RPC=OFF`. Recheck the upstream
advisory list before changing or shipping the pin.
