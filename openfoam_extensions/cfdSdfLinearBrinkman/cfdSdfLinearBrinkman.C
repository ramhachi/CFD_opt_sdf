/*---------------------------------------------------------------------------*\\
  =========                 |
  \\      /  F ield         | CFD_opt_sdf project extension
   \\    /   O peration     |
    \\  /    A nd           |
     \\/     M anipulation  |
-------------------------------------------------------------------------------
\\*---------------------------------------------------------------------------*/

#include "cfdSdfLinearBrinkman.H"

#include "addToRunTimeSelectionTable.H"
#include "fvmSup.H"
#include "PstreamReduceOps.H"

#include <cmath>

namespace Foam
{
namespace fv
{

defineTypeNameAndDebug(cfdSdfLinearBrinkman, 0);
addToRunTimeSelectionTable(option, cfdSdfLinearBrinkman, dictionary);

} // End namespace fv
} // End namespace Foam


Foam::fv::cfdSdfLinearBrinkman::cfdSdfLinearBrinkman
(
    const word& name,
    const word& modelType,
    const dictionary& dict,
    const fvMesh& mesh
)
:
    cellSetOption(name, modelType, dict, mesh),
    betaFieldName_(word::null),
    UName_(word::null),
    betaMax_("betaMax", dimless/dimTime, Zero),
    betaFieldPtr_(nullptr),
    resistanceFieldName_(word::null),
    resistanceFieldPtr_(nullptr),
    configured_(false)
{
    read(dict);
    ensureBetaField();

    if (mesh_.foundObject<volVectorField>(resistanceFieldName_))
    {
        FatalIOErrorInFunction(dict)
            << "resistanceField '" << resistanceFieldName_
            << "' already exists.  The cfdSdfLinearBrinkman output field "
            << "must have a unique name."
            << exit(FatalIOError);
    }

    resistanceFieldPtr_.reset
    (
        new volVectorField
        (
            IOobject
            (
                resistanceFieldName_,
                mesh_.time().timeName(),
                mesh_,
                IOobject::NO_READ,
                IOobject::AUTO_WRITE
            ),
            mesh_,
            dimensionedVector
            (
                "zero",
                dimLength/sqr(dimTime),
                Zero
            ),
            fvPatchFieldBase::zeroGradientType()
        )
    );
}


void Foam::fv::cfdSdfLinearBrinkman::ensureBetaField()
{
    if (mesh_.foundObject<volScalarField>(betaFieldName_))
    {
        return;
    }

    betaFieldPtr_.reset
    (
        new volScalarField
        (
            IOobject
            (
                betaFieldName_,
                mesh_.time().timeName(),
                mesh_,
                IOobject::MUST_READ,
                IOobject::NO_WRITE
            ),
            mesh_
        )
    );
}


const Foam::volScalarField& Foam::fv::cfdSdfLinearBrinkman::beta() const
{
    if (!mesh_.foundObject<volScalarField>(betaFieldName_))
    {
        FatalErrorInFunction
            << type() << " requires explicit volScalarField betaField '"
            << betaFieldName_ << "' to be present before simpleFoam starts"
            << exit(FatalError);
    }

    return mesh_.lookupObject<volScalarField>(betaFieldName_);
}


void Foam::fv::cfdSdfLinearBrinkman::validateContract
(
    const volScalarField& betaField
) const
{
    if (betaMax_.dimensions() != dimless/dimTime)
    {
        FatalErrorInFunction
            << "betaMax must have dimensions [0 0 -1 0 0 0 0], got "
            << betaMax_.dimensions()
            << exit(FatalError);
    }

    if (!std::isfinite(betaMax_.value()) || betaMax_.value() <= SMALL)
    {
        FatalErrorInFunction
            << "betaMax must be finite and greater than zero, got "
            << betaMax_.value()
            << exit(FatalError);
    }

    if (betaField.dimensions() != dimless)
    {
        FatalErrorInFunction
            << "betaField '" << betaFieldName_
            << "' must be dimensionless, got " << betaField.dimensions()
            << exit(FatalError);
    }

    scalar minBeta = GREAT;
    scalar maxBeta = -GREAT;
    bool nonFiniteBeta = false;

    forAll(betaField, celli)
    {
        const scalar value = betaField[celli];
        minBeta = min(minBeta, value);
        maxBeta = max(maxBeta, value);
        nonFiniteBeta = nonFiniteBeta || !std::isfinite(value);
    }

    reduce(minBeta, minOp<scalar>());
    reduce(maxBeta, maxOp<scalar>());
    reduce(nonFiniteBeta, orOp<bool>());

    if (nonFiniteBeta || minBeta < -SMALL || maxBeta > scalar(1) + SMALL)
    {
        FatalErrorInFunction
            << "betaField '" << betaFieldName_
            << "' must contain only finite values in [0, 1]; observed "
            << "min=" << minBeta << ", max=" << maxBeta
            << exit(FatalError);
    }
}


void Foam::fv::cfdSdfLinearBrinkman::updateResistanceField
(
    const volScalarField& betaField,
    const volVectorField& U
)
{
    volVectorField& resistance = resistanceFieldPtr_();
    vectorField& resistanceInternal = resistance.primitiveFieldRef();
    const scalarField& betaInternal = betaField.primitiveField();
    const vectorField& UInternal = U.primitiveField();

    forAll(resistanceInternal, celli)
    {
        resistanceInternal[celli] =
            betaMax_.value()*betaInternal[celli]*UInternal[celli];
    }

    resistance.correctBoundaryConditions();
}


void Foam::fv::cfdSdfLinearBrinkman::addBrinkmanSink
(
    fvMatrix<vector>& eqn
)
{
    const volScalarField& betaField = beta();
    validateContract(betaField);

    const volVectorField& U = eqn.psi();
    if (U.name() != UName_)
    {
        FatalErrorInFunction
            << type() << " is configured for U field '" << UName_
            << "' but received equation for '" << U.name() << "'"
            << exit(FatalError);
    }

    updateResistanceField(betaField, U);

    // fvOptions sources are placed on the RHS.  Subtracting a positive
    // fvm::Sp term therefore gives the required RHS sink -betaMax*beta*U,
    // while retaining it implicitly in the assembled momentum matrix.
    eqn -= fvm::Sp(betaMax_*betaField, U);
}


void Foam::fv::cfdSdfLinearBrinkman::addSup
(
    fvMatrix<vector>& eqn,
    const label fieldI
)
{
    addBrinkmanSink(eqn);
}


void Foam::fv::cfdSdfLinearBrinkman::correct(volVectorField& U)
{
    if (U.name() != UName_)
    {
        return;
    }

    const volScalarField& betaField = beta();
    validateContract(betaField);
    updateResistanceField(betaField, U);
}


bool Foam::fv::cfdSdfLinearBrinkman::read(const dictionary& dict)
{
    if (!cellSetOption::read(dict))
    {
        return false;
    }

    if (selectionMode_ != smAll)
    {
        FatalIOErrorInFunction(dict)
            << type() << " requires selectionMode all, because betaField "
            << "already declares the full Cartesian porous design domain"
            << exit(FatalIOError);
    }

    const word candidateU = coeffs_.get<word>("U");
    const word candidateBeta = coeffs_.get<word>("betaField");
    const word candidateResistance = coeffs_.get<word>("resistanceField");
    const dimensionedScalar candidateBetaMax
    (
        coeffs_.get<dimensionedScalar>("betaMax")
    );

    if (candidateBetaMax.dimensions() != dimless/dimTime)
    {
        FatalIOErrorInFunction(dict)
            << "betaMax must have dimensions [0 0 -1 0 0 0 0], got "
            << candidateBetaMax.dimensions()
            << exit(FatalIOError);
    }

    if (!std::isfinite(candidateBetaMax.value()) || candidateBetaMax.value() <= SMALL)
    {
        FatalIOErrorInFunction(dict)
            << "betaMax must be finite and greater than zero, got "
            << candidateBetaMax.value()
            << exit(FatalIOError);
    }

    if (configured_)
    {
        if
        (
            candidateU != UName_
         || candidateBeta != betaFieldName_
         || candidateResistance != resistanceFieldName_
         || candidateBetaMax.value() != betaMax_.value()
         || candidateBetaMax.dimensions() != betaMax_.dimensions()
        )
        {
            FatalIOErrorInFunction(dict)
                << type() << " contract is immutable after startup.  "
                << "Do not change U, betaField, betaMax, or resistanceField "
                << "during a run."
                << exit(FatalIOError);
        }
    }
    else
    {
        UName_ = candidateU;
        betaFieldName_ = candidateBeta;
        resistanceFieldName_ = candidateResistance;
        betaMax_ = candidateBetaMax;
        fieldNames_.setSize(1);
        fieldNames_[0] = UName_;
        resetApplied();
        configured_ = true;
    }

    return true;
}

// ************************************************************************* //
