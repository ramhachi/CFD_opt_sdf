#ifndef objectivePorousDirectionalForce_H
#define objectivePorousDirectionalForce_H

#include "objectiveIncompressible.H"

namespace Foam
{

class topOVariablesBase;

namespace objectives
{

class objectivePorousDirectionalForce
:
    public objectiveIncompressible
{
    // Cell zones over which the Brinkman reaction is integrated.
    labelList zones_;

    // Integrate every cell when no zone selection is supplied.
    bool allCells_;

    // Unit vector defining the positive force direction.
    vector direction_;

    // Converts the kinematic Brinkman reaction to a force coefficient.
    scalar coefficientScale_;

    const topOVariablesBase& topOVars() const;

public:

    TypeName("porousDirectionalForce");

    objectivePorousDirectionalForce
    (
        const fvMesh& mesh,
        const dictionary& dict,
        const word& adjointSolverName,
        const word& primalSolverName
    );

    virtual ~objectivePorousDirectionalForce() = default;

    virtual scalar J();

    virtual void update_dJdv();

    virtual void update_dJdb();
};

} // End namespace objectives
} // End namespace Foam

#endif
