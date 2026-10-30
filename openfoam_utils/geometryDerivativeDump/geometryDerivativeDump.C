/*---------------------------------------------------------------------------*\
Application
    geometryDerivativeDump
Description
    Read-only dump of the registered-direction B-spline geometry derivatives
    of the design patch. The utility never moves the mesh: it contracts the
    OpenFOAM analytic dxdbFace, dSdb and dndb tensors with the registered
    control-point weight fields and writes the per-face directional
    derivatives, plus the per-patch count of points inside the control-point
    box. No field or mesh is written.
\*---------------------------------------------------------------------------*/

#include "argList.H"
#include "Time.H"
#include "fvMesh.H"
#include "volBSplinesBase.H"
#include "NURBS3DVolume.H"
#include "IOdictionary.H"
#include "OFstream.H"

using namespace Foam;

int main(int argc, char* argv[])
{
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createNamedMesh.H"

    const word designPatchName("design_candidate");

    IOdictionary settings
    (
        IOobject
        (
            "geometryDerivativeDirections",
            runTime.constant(),
            mesh,
            IOobject::MUST_READ,
            IOobject::NO_WRITE,
            IOobject::NO_REGISTER
        )
    );
    const wordList names(settings.lookup("names"));
    const fileName subDir
    (
        settings.getOrDefault<fileName>("directory", "geometryDerivativeDirections")
    );

    volBSplinesBase& base =
        const_cast<volBSplinesBase&>(volBSplinesBase::New(mesh));
    if (base.getNumberOfBoxes() != 1)
    {
        FatalErrorInFunction
            << "the registered Work F parameterization has exactly one box, found "
            << base.getNumberOfBoxes() << exit(FatalError);
    }
    const label nCPs(base.getTotalControlPointsNumber());
    NURBS3DVolume& box = base.boxRef(0);
    const labelList& reverseMap = box.getReverseMap();

    const polyBoundaryMesh& patches = mesh.boundaryMesh();
    const label designPatchI = patches.findPatchID(designPatchName);
    if (designPatchI < 0)
    {
        FatalErrorInFunction
            << "the mesh lacks the " << designPatchName << " patch" << exit(FatalError);
    }
    const polyPatch& designPatch = patches[designPatchI];
    const label nFaces(designPatch.size());

    PtrList<vectorField> weights(names.size());
    forAll(names, i)
    {
        IOdictionary weightDict
        (
            IOobject
            (
                names[i],
                runTime.constant()/subDir,
                mesh,
                IOobject::MUST_READ,
                IOobject::NO_WRITE,
                IOobject::NO_REGISTER
            )
        );
        weights.set(i, new vectorField(weightDict.lookup("weights")));
        if (weights[i].size() != nCPs)
        {
            FatalErrorInFunction
                << "direction " << names[i] << " has " << weights[i].size()
                << " weights but the parameterization has " << nCPs
                << " control points" << exit(FatalError);
        }
    }

    List<vectorField> dCf(names.size(), vectorField(nFaces, Zero));
    List<vectorField> dSf(names.size(), vectorField(nFaces, Zero));
    List<vectorField> dn(names.size(), vectorField(nFaces, Zero));

    for (label cpI = 0; cpI < nCPs; ++cpI)
    {
        const tensorField dC(box.patchDxDbFace(designPatchI, cpI));
        const tensorField dS(box.dndbBasedSensitivities(designPatchI, cpI, true));
        const tensorField dN(box.dndbBasedSensitivities(designPatchI, cpI, false));
        if (dC.size() != nFaces || dS.size() != nFaces || dN.size() != nFaces)
        {
            FatalErrorInFunction << "unexpected face field size" << exit(FatalError);
        }
        forAll(names, i)
        {
            const vector& w = weights[i][cpI];
            if (magSqr(w) <= VSMALL) continue;
            for (label fI = 0; fI < nFaces; ++fI)
            {
                dCf[i][fI] += dC[fI] & w;
                dSf[i][fI] += dS[fI] & w;
                dn[i][fI] += dN[fI] & w;
            }
        }
    }

    OFstream os(runTime.path()/"geometryDerivatives.dat");
    os.precision(17);
    os << "#geometryDerivativeDump v1" << nl;
    os << "#design_patch " << designPatchName << nl;
    os << "#n_design_faces " << nFaces << nl;
    os << "#n_control_points " << nCPs << nl;
    forAll(names, i)
    {
        os << "#direction " << names[i] << nl;
        os << "#face_table_begin " << names[i] << nl;
        forAll(dCf[i], fI)
        {
            os  << fI
                << token::SPACE << dCf[i][fI].x()
                << token::SPACE << dCf[i][fI].y()
                << token::SPACE << dCf[i][fI].z()
                << token::SPACE << dSf[i][fI].x()
                << token::SPACE << dSf[i][fI].y()
                << token::SPACE << dSf[i][fI].z()
                << token::SPACE << dn[i][fI].x()
                << token::SPACE << dn[i][fI].y()
                << token::SPACE << dn[i][fI].z()
                << nl;
        }
        os << "#face_table_end " << names[i] << nl;
    }
    os << "#patch_inside_counts_begin" << nl;
    forAll(patches, pI)
    {
        label inside(0);
        for (const label pointi : patches[pI].meshPoints())
        {
            if (reverseMap[pointi] != -1) inside++;
        }
        os << patches[pI].name() << token::SPACE << inside << nl;
    }
    os << "#patch_inside_counts_end" << nl;
    os << "#end" << nl;

    Info<< "geometryDerivativeDump: wrote analytic derivatives for "
        << names.size() << " directions over " << nFaces << " design faces" << endl;
    Info<< "End\n" << endl;
    return 0;
}

// ************************************************************************* //
