#include "stagedRawAlphaGradientExporter.H"

#include "addToRunTimeSelectionTable.H"
#include "Pstream.H"
#include "Time.H"

#include <cctype>
#include <cmath>

namespace Foam
{

defineTypeNameAndDebug(stagedRawAlphaGradientExporter, 0);
addToRunTimeSelectionTable(functionObject, stagedRawAlphaGradientExporter, dictionary);


stagedRawAlphaGradientExporter::stagedRawAlphaGradientExporter
(
    const word& name,
    const Time& runTime,
    const dictionary& dict
)
:
    functionObject(name),
    name_(name),
    runTime_(runTime)
{
    validateContract(dict);
    rejectUnavailableApi();
}


void stagedRawAlphaGradientExporter::validateContract
(
    const dictionary& dict
) const
{
    // These values are deliberately read by name.  They are the minimum
    // response-specific provenance required for a future native artifact.
    const word flowCaseId(dict.get<word>("flowCaseId"));
    const word responseId(dict.get<word>("responseId"));
    const word namedAdjointId(dict.get<word>("namedAdjointId"));
    const word gradientVariable(dict.get<word>("gradientVariable"));
    const string derivativeMeaning(dict.get<string>("derivativeMeaning"));
    const string internalChain(dict.get<string>("internalChain"));
    const string rawCoefficientFormula(dict.get<string>("rawCoefficientFormula"));
    const string rawCoefficientUnits(dict.get<string>("rawCoefficientUnits"));
    const scalar newtonConversionFactor(dict.get<scalar>("newtonConversionFactor"));
    const string newtonConversionFormula(dict.get<string>("newtonConversionFormula"));
    const string newtonConversionUnits(dict.get<string>("newtonConversionUnits"));
    const fileName sourcePath(dict.get<fileName>("sourcePath"));
    const string sourceSha256(dict.get<string>("sourceSha256"));

    if
    (
        !flowCaseId.size() || !responseId.size() || !namedAdjointId.size()
     || gradientVariable != "staged_raw_alpha"
     || derivativeMeaning != "dJ=sum_i g_alpha[i]*d(alpha_i)"
     || internalChain != "alpha->alphaTilda->beta->response"
     || !rawCoefficientFormula.size() || !rawCoefficientUnits.size()
     || !std::isfinite(newtonConversionFactor)
     || !newtonConversionFormula.size() || !newtonConversionUnits.size()
     || !sourcePath.size() || sourceSha256.size() != 64
    )
    {
        FatalIOErrorInFunction(dict)
            << "stagedRawAlphaGradientExporter requires explicit response "
            << "identity and a complete staged_raw_alpha provenance contract"
            << exit(FatalIOError);
    }

    forAll(sourceSha256, charIndex)
    {
        const char c = sourceSha256[charIndex];
        if (!std::isxdigit(static_cast<unsigned char>(c)))
        {
            FatalIOErrorInFunction(dict)
                << "sourceSha256 must be exactly 64 hexadecimal characters"
                << exit(FatalIOError);
        }
    }

    if (Pstream::parRun())
    {
        FatalIOErrorInFunction(dict)
            << "stagedRawAlphaGradientExporter is serial-only for G2 "
            << "qualification; processor ordering is not an accepted export "
            << "contract"
            << exit(FatalIOError);
    }
}


void stagedRawAlphaGradientExporter::rejectUnavailableApi() const
{
    FatalErrorInFunction
        << "No audited OpenFOAM solver API is available in this build to "
        << "export dJ/d(staged_raw_alpha) after the exact "
        << "alpha->alphaTilda->beta->response chain for function object "
        << name_ << " at final time " << runTime_.timeName() << nl
        << "No native field or metadata artifact was written.  Do not "
        << "substitute a beta derivative or an undeclared legacy sensitivity "
        << "field.  Add a solver API that returns a certified, response-specific "
        << "staged_raw_alpha derivative and its source provenance before enabling "
        << "this exporter."
        << exit(FatalError);
}


bool stagedRawAlphaGradientExporter::read(const dictionary& dict)
{
    validateContract(dict);
    rejectUnavailableApi();
    return false;
}


bool stagedRawAlphaGradientExporter::execute()
{
    rejectUnavailableApi();
    return false;
}


bool stagedRawAlphaGradientExporter::write()
{
    rejectUnavailableApi();
    return false;
}


bool stagedRawAlphaGradientExporter::end()
{
    return true;
}

} // End namespace Foam
