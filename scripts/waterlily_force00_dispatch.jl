#!/usr/bin/env julia
# The literal FORCE-00 copy intentionally retains the registered flow_32
# inventory. This optional launcher selects F1's flow_24 without modifying that
# copy, any registered job, or any solver/measurement/window/phase expression.
# Usage: FORCE00_CASE=flow_24 FORCE00_CV_BOX='lo:hi,lo:hi,lo:hi' \
#   julia --project=julia/CFDSDFWaterLily scripts/waterlily_force00_dispatch.jl \
#   <phi_fortran.raw> <output_dir>

function force00_case_expression(expression, case_id)
    case_id in ("flow_24", "flow_32") ||
        throw(ArgumentError("FORCE00_CASE must be flow_24 or flow_32"))
    expression isa Expr || return expression
    if expression.head == :const && expression.args[1] isa Expr &&
       expression.args[1].head == :(=) && expression.args[1].args[1] == :EXPECTED_CASE_IDS
        expression.args[1].args[2] == Expr(:tuple, "flow_32") ||
            error("FORCE-00 copied case inventory drift")
        return :(const EXPECTED_CASE_IDS = ($case_id,))
    elseif expression.head == :function && expression.args[1] == Expr(:call, :main)
        filters = Ref(0)
        function select_case(node)
            # Replace only the predicate c.case_id == "flow_32", not messages,
            # defaults, file paths, constants, or numerical expressions.
            if node == :(c.case_id == "flow_32")
                filters[] += 1
                return :(c.case_id == $case_id)
            end
            node isa Expr || return node
            return Expr(node.head, select_case.(node.args)...)
        end
        selected = select_case(expression)
        filters[] == 1 || error("FORCE-00 copied main must contain exactly one case predicate")
        return selected
    end
    return expression
end

if abspath(PROGRAM_FILE) == @__FILE__
    selected_case = ENV["FORCE00_CASE"] # required; no silent F1/F2 default
    selected_case in ("flow_24", "flow_32") ||
        throw(ArgumentError("FORCE00_CASE must be flow_24 or flow_32"))
    Base.include(expression -> force00_case_expression(expression, selected_case),
        Main, joinpath(@__DIR__, "waterlily_force00_job.jl"))
end
