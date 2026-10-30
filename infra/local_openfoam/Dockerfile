# Local OpenFOAM v2512 runtime for the registered Kaggle CPU runners (decision 2026-10-20, docs/local_openfoam_env_gate_2026_10_20.md).
# linux/amd64 (Rosetta on Apple silicon) because every registered runner hard-requires amd64 and an OpenCFD lock chosen by the Ubuntu codename;
# Ubuntu 24.04.5 noble = the OS the Kaggle CPU runtime reports (T2-0b, T2-0c smoke, X3 formal). Build with scripts/local_openfoam.py build.
FROM ubuntu:24.04@sha256:a2d43bffc46670d7108bb3c0468c67c5557c4c92e83e1e34cbff1322ad1b94dc
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
# gnupg: the official OpenCFD repository installer needs it; the GL libraries are the ones the T2-0b/T2-0c runners install when the gmsh wheel
# fails to import. The apt lists are kept (as on Kaggle): the runners' own install_openfoam runs again at every start and must find them.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git gnupg python3 python3-venv \
      libglu1-mesa libgl1 libxft2 libxinerama1 libxcursor1 libxrender1 libxfixes3
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/py && /opt/py/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
ENV PATH=/opt/py/bin:$PATH
# OpenFOAM is installed by the registered X3 formal runner's own install_openfoam (official installer, index and .deb SHA-256 from the locks);
# its work directory must be absolute (apt-get install treats a bare .deb file name as a package name)
COPY runner_x3_formal.py openfoam_package_lock_jammy.json openfoam_package_lock_noble.json /tmp/of/
RUN cd /tmp/of && python -c "import json, pathlib, runner_x3_formal as r; \
locks = {s: json.loads(pathlib.Path(f'openfoam_package_lock_{s}.json').read_text()) for s in ('jammy', 'noble')}; \
print(json.dumps(r.install_openfoam(pathlib.Path('/tmp/of'), locks, 'OpenFOAM-v2512')))" && rm -rf /tmp/of
WORKDIR /kaggle/working
