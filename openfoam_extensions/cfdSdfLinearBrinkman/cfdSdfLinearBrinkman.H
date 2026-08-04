/*---------------------------------------------------------------------------*\\
  =========                 |
  \\      /  F ield         | CFD_opt_sdf project extension
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
Class
    Foam::fv::cfdSdfLinearBrinkman

Description
    A project-owned, incompressible linear Brinkman momentum sink for
    OpenCFD OpenFOAM v2512.  It applies the exact kinematic source

        Su(U) = - betaMax * beta * U

    where beta is an explicit, dimensionless 0..1 volume field (0 fluid,
    1 solid) and betaMax has dimensions 1/time.  The sink is implicit in U.

    The accompanying resistanceField is a positive resistance acceleration,

        resistanceField = betaMax * beta * U,

    so its density-weighted volume integral is the total porous resistance.
    It is deliberately not a pressure or viscous-force decomposition.

    This class is independent of topOSource and topOVariablesBase.

SourceFiles
    cfdSdfLinearBrinkman.C

\\*---------------------------------------------------------------------------*/

#ifndef Foam_fv_cfdSdfLinearBrinkman_H
#define Foam_fv_cfdSdfLinearBrinkman_H

#include "cellSetOption.H"
#include "volFields.H"

namespace Foam
{
namespace fv
{

class cfdSdfLinearBrinkman
:
    public cellSetOption
{
    //- Name of the explicit, dimensionless [0,1] solid fraction field
    word betaFieldName_;

    //- Name of the incompressible velocity field to which the sink applies
    word UName_;

    //- Kinematic maximum Brinkman coefficient [1/s]
    dimensionedScalar betaMax_;

    //- Ownership when simpleFoam has not already registered betaField.
    //  The field is always explicitly MUST_READ from the case at startup.
    autoPtr<volScalarField> betaFieldPtr_;

    //- Name of the positive resistance-acceleration output field
    word resistanceFieldName_;

    //- Auto-written betaMax*beta*U [m/s2], for total porous-force reduction
    autoPtr<volVectorField> resistanceFieldPtr_;

    //- Read once at construction; later changes of the contract fail closed
    bool configured_;

    //- Look up and validate the explicit beta field
    const volScalarField& beta() const;

    //- Load and register betaField when the solver has not read it itself
    void ensureBetaField();

    //- Validate betaMax and all internal beta values before every use
    void validateContract(const volScalarField& betaField) const;

    //- Write the positive resistance acceleration from the current U field
    void updateResistanceField
    (
        const volScalarField& betaField,
        const volVectorField& U
    );

    //- Build a matrix source representing the RHS sink -betaMax*beta*U
    void addBrinkmanSink(fvMatrix<vector>& eqn);

public:

    TypeName("cfdSdfLinearBrinkman");

    cfdSdfLinearBrinkman
    (
        const word& name,
        const word& modelType,
        const dictionary& dict,
        const fvMesh& mesh
    );

    cfdSdfLinearBrinkman(const cfdSdfLinearBrinkman&) = delete;
    void operator=(const cfdSdfLinearBrinkman&) = delete;

    virtual ~cfdSdfLinearBrinkman() = default;

    //- Add the implicit kinematic momentum sink for simpleFoam
    virtual void addSup(fvMatrix<vector>& eqn, const label fieldI);

    //- Update the output field after simpleFoam corrects U
    virtual void correct(volVectorField& U);

    //- Read and fail closed if a running case attempts to change the contract
    virtual bool read(const dictionary& dict);
};

} // End namespace fv
} // End namespace Foam

#endif

// ************************************************************************* //
