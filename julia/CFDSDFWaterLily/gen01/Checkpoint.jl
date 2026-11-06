"""
Data-only checkpoints for WaterLily 1.8.0's standard Flow/MultiLevelPoisson path.

The caller reconstructs the identical body/configuration and resumes with the
default `remeasure=true`. Body closures, GPU pointers and RNG state are excluded.
Only deserialize trusted files made by this code under the same locked runtime.
"""
module Checkpoint

using Serialization, SHA, WaterLily
export save_checkpoint, load_checkpoint, restore_checkpoint!

const MAGIC = "CFDSDF-WATERLILY-CHECKPOINT-1\n"

function configuration(sim)
    sim.flow isa WaterLily.Flow && sim.pois isa WaterLily.MultiLevelPoisson ||
        throw(ArgumentError("checkpoint supports the standard Flow/MultiLevelPoisson only"))
    project = Base.active_project()
    manifest = isnothing(project) ? "" : joinpath(dirname(project), "Manifest.toml")
    isfile(manifest) || throw(ArgumentError("checkpoint requires an active locked Manifest.toml"))
    f = sim.flow
    (julia_version=string(VERSION), waterlily_version=string(pkgversion(WaterLily)),
     manifest_sha256=bytes2hex(sha256(read(manifest))),
     velocity_shape=size(f.u), pressure_shape=size(f.p), dtype=string(eltype(f.u)),
     U=sim.U, L=sim.L, ϵ=sim.ϵ, ν=f.ν, perdir=f.perdir, exitBC=f.exitBC,
     boundary=f.uBC isa Tuple ? f.uBC : string(typeof(f.uBC)),
     acceleration=string(typeof(f.g)), scheme=string(typeof(f.λ)),
     body_type=string(typeof(sim.body)))
end

function validate(data)
    data isa NamedTuple || throw(ArgumentError("checkpoint payload must be a NamedTuple"))
    required = (:schema_version, :configuration, :identity, :u, :p, :u⁰, :Δt,
                :time, :sim_time, :step, :rows)
    all(k -> hasproperty(data, k), required) || throw(ArgumentError("incomplete checkpoint payload"))
    data.schema_version == 1 || throw(ArgumentError("unknown checkpoint schema"))
    data.identity isa AbstractString || throw(ArgumentError("checkpoint identity must be a string"))
    data.step isa Integer && data.step >= 0 || throw(ArgumentError("invalid checkpoint step"))
    data.Δt isa Vector && length(data.Δt) == data.step + 1 ||
        throw(ArgumentError("checkpoint step does not match timestep history"))
    all(x -> isfinite(x) && x > 0, data.Δt) || throw(ArgumentError("invalid timestep history"))
    for field in (:u, :p, :u⁰)
        a = getproperty(data, field)
        a isa Array && all(isfinite, a) || throw(ArgumentError("non-finite or invalid $field field"))
    end
    size(data.u) == size(data.u⁰) == data.configuration.velocity_shape ||
        throw(ArgumentError("checkpoint velocity shape mismatch"))
    size(data.p) == data.configuration.pressure_shape ||
        throw(ArgumentError("checkpoint pressure shape mismatch"))
    string(eltype(data.u)) == string(eltype(data.u⁰)) == string(eltype(data.p)) ==
        data.configuration.dtype || throw(ArgumentError("checkpoint field type mismatch"))
    data.time == sum(@view(data.Δt[1:end-1])) &&
        data.sim_time == data.time * data.configuration.U / data.configuration.L ||
        throw(ArgumentError("checkpoint time does not match timestep history"))
    data.rows isa AbstractVector && all(row -> all(isfinite, row), data.rows) ||
        throw(ArgumentError("checkpoint sample rows must be finite"))
    return data
end

"""
    save_checkpoint(path, sim, step, rows; identity="") -> path

Atomically replace `path` at a completed solver step. Host arrays preserve u,
p, u⁰ and the entire adaptive Δt history. `identity` is caller-supplied study,
geometry and sampling identity; the caller must compare it before restoring.
Existing checkpoints survive a process kill before the final rename.
"""
function save_checkpoint(path, sim, step, rows; identity="")
    data = validate((schema_version=1, configuration=configuration(sim),
        identity=identity, u=Array(sim.flow.u), p=Array(sim.flow.p), u⁰=Array(sim.flow.u⁰),
        Δt=copy(sim.flow.Δt), time=WaterLily.time(sim), sim_time=sim_time(sim),
        step=step, rows=copy(rows)))
    mkpath(dirname(abspath(path)))
    temporary, io = mktemp(dirname(abspath(path)))
    try
        write(io, MAGIC)
        serialize(io, data)
        close(io)
        # Same-directory rename is atomic on the local filesystems used by WSL2.
        Base.Filesystem.rename(temporary, path)
    finally
        isopen(io) && close(io)
        ispath(temporary) && rm(temporary)
    end
    return path
end

"""Load a trusted, complete checkpoint and return its validated NamedTuple."""
function load_checkpoint(path)
    try
        open(path, "r") do io
            String(read(io, ncodeunits(MAGIC))) == MAGIC ||
                throw(ArgumentError("checkpoint header mismatch"))
            data = validate(deserialize(io))
            eof(io) || throw(ArgumentError("unexpected bytes after checkpoint payload"))
            data
        end
    catch err
        err isa InterruptException && rethrow()
        throw(ArgumentError("cannot load checkpoint $(path): $(sprint(showerror, err))"))
    end
end

"""
    restore_checkpoint!(sim, checkpoint) -> sim

Restore into a freshly constructed identical simulation. A new pressure solver
provides zeroed ghost/work buffers; default remeasurement rebuilds its coefficients
before the next step. Custom flows/solvers, RNG-driven jobs, changed body functions
and `remeasure=false` are outside this interface's verified contract.
"""
function restore_checkpoint!(sim, data)
    validate(data)
    isequal(configuration(sim), data.configuration) ||
        throw(ArgumentError("checkpoint runtime or simulation configuration mismatch"))
    length(sim.flow.Δt) == 1 && isempty(sim.pois.n) ||
        throw(ArgumentError("restore requires a newly constructed simulation"))
    for field in (:u, :p, :u⁰)
        copyto!(getproperty(sim.flow, field), getproperty(data, field))
    end
    empty!(sim.flow.Δt)
    append!(sim.flow.Δt, data.Δt)
    return sim
end

end # module Checkpoint
