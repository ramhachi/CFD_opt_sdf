#include "objectivePorousDirectionalForce.H"

#include "addToRunTimeSelectionTable.H"
#include "createZeroField.H"
#include "solver.H"
#include "topOVariablesBase.H"

namespace Foam
{
namespace objectives
{

defineTypeNameAndDebug(objectivePorousDirectionalForce, 0);
addToRunTimeSelectionTable
(
    objectiveIncompressible,
    objectivePorousDirectionalForce,
    dictionary
);


const topOVariablesBase&
objectivePorousDirectionalForce::topOVars() const
{
    if (!mesh_.foundObject<topOVariablesBase>("topOVars"))
    {
        FatalErrorInFunction
            << type() << " requires topO design variables named topOVars"
            << exit(FatalError);
    }

    return mesh_.lookupObject<topOVariablesBase>("topOVars");
}


objectivePorousDirectionalForce::objectivePorousDirectionalForce
(
    const fvMesh& mesh,
    const dictionary& dict,
    const word& adjointSolverName,
    const word& primalSolverName
)
:
    objectiveIncompressible(mesh, dict, adjointSolverName, primalSolverName),
    zones_
    (
        dict.found("zones")
      ? mesh_.cellZones().indices(dict.get<wordRes>("zones"))
      : labelList()
    ),
    allCells_(!dict.found("zones")),
    direction_(dict.get<vector>("direction")),
    coefficientScale_(Zero)
{
    const scalar directionMagnitude = mag(direction_);
    if (directionMagnitude < SMALL)
    {
        FatalIOErrorInFunction(dict)
            << "direction must be non-zero"
            << exit(FatalIOError);
    }
    direction_ /= directionMagnitude;

    const scalar referenceArea = dict.get<scalar>("Aref");
    const scalar referenceVelocity = dict.get<scalar>("UInf");
    if (referenceArea <= SMALL || mag(referenceVelocity) <= SMALL)
    {
        FatalIOErrorInFunction(dict)
            << "Aref and |UInf| must be greater than zero"
            << exit(FatalIOError);
    }
    coefficientScale_ = 2.0/(referenceArea*sqr(referenceVelocity));

    if (!allCells_)
    {
        checkCellZonesSize(zones_);
    }

    fieldNames_.setSize
    (
        1,
        mesh_.lookupObject<solver>(adjointSolverName_).
            extendedVariableName("Ua")
    );

    dJdvPtr_.reset
    (
        createZeroFieldPtr<vector>
        (
            mesh_,
            "dJdv" + objectiveName_,
            dimLength/sqr(dimTime)
        )
    );

    dJdbPtr_.reset
    (
        createZeroFieldPtr<scalar>
        (
            mesh_,
            "dJdb" + objectiveName_,
            dimless
        )
    );
}


scalar objectivePorousDirectionalForce::J()
{
    J_ = Zero;

    const topOVariablesBase& topology = topOVars();
    const volScalarField& beta = topology.beta();
    const volVectorField& U = vars_.UInst();
    const scalarField& V = mesh_.V().field();

    scalar localReaction = Zero;
    if (allCells_)
    {
        forAll(beta, cellIndex)
        {
            localReaction +=
                beta[cellIndex]
               *(U[cellIndex] & direction_)
               *V[cellIndex];
        }
    }
    else
    {
        for (const label zoneIndex : zones_)
        {
            const cellZone& zone = mesh_.cellZones()[zoneIndex];
            for (const label cellIndex : zone)
            {
                localReaction +=
                    beta[cellIndex]
                   *(U[cellIndex] & direction_)
                   *V[cellIndex];
            }
        }
    }

    J_ =
        coefficientScale_
       *topology.getBetaMax()
       *returnReduce(localReaction, sumOp<scalar>());

    return J_;
}


void objectivePorousDirectionalForce::update_dJdv()
{
    vectorField& dJdv = dJdvPtr_().primitiveFieldRef();
    dJdv = Zero;

    const topOVariablesBase& topology = topOVars();
    const volScalarField& beta = topology.beta();
    const scalar multiplier =
        coefficientScale_*topology.getBetaMax();

    if (allCells_)
    {
        forAll(beta, cellIndex)
        {
            dJdv[cellIndex] =
                multiplier*beta[cellIndex]*direction_;
        }
    }
    else
    {
        for (const label zoneIndex : zones_)
        {
            const cellZone& zone = mesh_.cellZones()[zoneIndex];
            for (const label cellIndex : zone)
            {
                dJdv[cellIndex] =
                    multiplier*beta[cellIndex]*direction_;
            }
        }
    }
}


void objectivePorousDirectionalForce::update_dJdb()
{
    scalarField& dJdb = dJdbPtr_().primitiveFieldRef();
    dJdb = Zero;

    const topOVariablesBase& topology = topOVars();
    const volVectorField& U = vars_.UInst();
    const scalar multiplier =
        coefficientScale_*topology.getBetaMax();

    if (allCells_)
    {
        forAll(U, cellIndex)
        {
            dJdb[cellIndex] =
                multiplier*(U[cellIndex] & direction_);
        }
    }
    else
    {
        for (const label zoneIndex : zones_)
        {
            const cellZone& zone = mesh_.cellZones()[zoneIndex];
            for (const label cellIndex : zone)
            {
                dJdb[cellIndex] =
                    multiplier*(U[cellIndex] & direction_);
            }
        }
    }
}

} // End namespace objectives
} // End namespace Foam
