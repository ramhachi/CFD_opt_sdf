/*---------------------------------------------------------------------------*\
Application
    moveControlPoints
Description
    Apply a prescribed control-point movement through the registered
    volumetricBSplines motion solver and write the moved mesh.
\*---------------------------------------------------------------------------*/

#include "argList.H"
#include "Time.H"
#include "fvMesh.H"
#include "motionSolver.H"
#include "volumetricBSplinesMotionSolver.H"
#include "IOdictionary.H"

using namespace Foam;

int main(int argc, char* argv[])
{
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createNamedMesh.H"

    IOdictionary movementDict
    (
        IOobject
        (
            "controlPointsMovement",
            runTime.constant(),
            mesh,
            IOobject::MUST_READ,
            IOobject::NO_WRITE,
            IOobject::NO_REGISTER
        )
    );
    vectorField movement(movementDict.lookup("controlPointsMovement"));

    autoPtr<motionSolver> motionPtr = motionSolver::New(mesh);
    auto& bSplineMotion = refCast<volumetricBSplinesMotionSolver>(motionPtr());

    bSplineMotion.setControlPointsMovement(movement);

    const pointField newPoints(bSplineMotion.curPoints());
    mesh.movePoints(newPoints);
    mesh.write();

    Info<< "moveControlPoints: applied " << movement.size()
        << " control-point movements" << endl;
    Info<< "End\n" << endl;
    return 0;
}
