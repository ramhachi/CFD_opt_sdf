# Front Wing Demo

Generate the sample STL files and project configuration:

```powershell
cfd-sdf init examples\front_wing
```

Then build the SDF cache and export ParaView files:

```powershell
cfd-sdf build-sdf examples\front_wing\project.yaml
cfd-sdf check-constraints examples\front_wing\project.yaml
cfd-sdf export-vtk examples\front_wing\project.yaml
```

The generated `project.yaml` is intentionally STL-only. Replace files in `geometry/` with real front-wing, tire, ground, vehicle, allowed-envelope, forbidden-envelope, and root-mount STLs as they become available.

For the one-command demo path from the repository root:

```powershell
.\scripts\run_front_wing_demo.ps1
```
