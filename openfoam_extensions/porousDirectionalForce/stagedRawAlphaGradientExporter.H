#ifndef stagedRawAlphaGradientExporter_H
#define stagedRawAlphaGradientExporter_H

#include "functionObject.H"

namespace Foam
{

/**
 * Fail-closed boundary for a response-specific staged-raw-alpha exporter.
 *
 * The current OpenCFD v2512 topO public API exposed to this extension gives
 * this project a direct objective derivative with respect to beta, but does
 * not expose an audited derivative after the complete
 * alpha -> alphaTilda -> beta -> response chain.  A beta derivative, or a
 * field selected by a familiar sensitivity filename, is not dJ/d(raw alpha).
 *
 * This function object therefore validates the explicit provenance contract
 * and aborts without publishing an artifact until a solver API can supply a
 * certified staged-raw-alpha derivative.  It is intentionally serial-only:
 * qualification must not depend on an implicit processor ordering.
 */
class stagedRawAlphaGradientExporter
:
    public functionObject
{
    word name_;
    const Time& runTime_;

    void validateContract(const dictionary& dict) const;
    void rejectUnavailableApi() const;

    stagedRawAlphaGradientExporter(const stagedRawAlphaGradientExporter&) = delete;
    void operator=(const stagedRawAlphaGradientExporter&) = delete;

public:

    TypeName("stagedRawAlphaGradientExporter");

    stagedRawAlphaGradientExporter
    (
        const word& name,
        const Time& runTime,
        const dictionary& dict
    );

    virtual ~stagedRawAlphaGradientExporter() = default;

    virtual bool read(const dictionary& dict);
    virtual bool execute();
    virtual bool write();
    virtual bool end();
};

} // End namespace Foam

#endif
