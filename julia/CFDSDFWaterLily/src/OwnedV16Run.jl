module CFDSDFW3RunOwnership

"""Strongly-owned W3 run bundle for a non-owning device SDF view."""
struct OwnedV16Run{O,B,S}
    owner::O
    bodies::B
    sim::S
end

end # module
