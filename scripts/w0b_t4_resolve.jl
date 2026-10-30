# W0b T4 environment resolve helper.
#
# Usage:
#   julia --project=<julia> scripts/w0b_t4_resolve.jl <project_dir>
#
# Activates the registered T4 environment directory, resolves the dependency
# graph from its deps-only Project.toml, and instantiates it.  Run on the
# explicitly selected T4 runtime.

using Pkg

length(ARGS) == 1 || error("usage: w0b_t4_resolve.jl <project_dir>")
project_dir = ARGS[1]
Pkg.activate(project_dir)
Pkg.resolve()
Pkg.instantiate()
Pkg.status()
println("W0B_RESOLVE_DONE ", project_dir)
