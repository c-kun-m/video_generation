"""Import an official Docker Hub image using the host proxy, without daemon config changes.

Uses OCI archives and verifies every manifest/blob digest. Requires Docker's containerd
image store and imports only linux/amd64. Cache archives live under ignored runtime/.
"""

import argparse
import hashlib
import json
import subprocess
import tarfile
import urllib.request
from pathlib import Path

REGISTRY = "https://registry-1.docker.io"
ACCEPT = (
    "application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.docker.distribution.manifest.v2+json"
)
ALLOWED = {
    "temporalio/server",
    "temporalio/admin-tools",
    "temporalio/ui",
    "library/postgres",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", choices=sorted(ALLOWED))
    parser.add_argument("tag")
    args = parser.parse_args()
    repository, tag = args.repository, args.tag
    cache = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "image-cache"
        / repository.replace("/", "-")
        / tag
    )
    blob_dir = cache / "blobs" / "sha256"
    blob_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(
        f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repository}:pull",
        timeout=30,
    ) as response:
        token = json.load(response)["token"]

    def request(path):
        return urllib.request.urlopen(
            urllib.request.Request(
                f"{REGISTRY}/v2/{repository}/{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT},
            ),
            timeout=60,
        )

    def verify(data, digest):
        if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError("Registry digest verification failed")

    with request(f"manifests/{tag}") as response:
        raw = response.read()
        root_digest = response.headers.get("Docker-Content-Digest")
        if not root_digest:
            raise RuntimeError("Registry did not return an immutable manifest digest")
        verify(raw, root_digest)
        manifest = json.loads(raw)
    if "manifests" in manifest:
        descriptor = next(
            m
            for m in manifest["manifests"]
            if m.get("platform", {}).get("os") == "linux"
            and m.get("platform", {}).get("architecture") == "amd64"
        )
        digest = descriptor["digest"]
        with request(f"manifests/{digest}") as response:
            raw = response.read()
        verify(raw, digest)
        manifest = json.loads(raw)
    else:
        digest = root_digest
    (blob_dir / digest.split(":")[1]).write_bytes(raw)
    for descriptor in [manifest["config"], *manifest["layers"]]:
        name = descriptor["digest"].split(":")[1]
        path = blob_dir / name
        if (
            path.exists()
            and hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == name
        ):
            continue
        print(
            f"Downloading verified blob {name[:12]} ({descriptor['size'] // 1024 // 1024} MiB)",
            flush=True,
        )
        temporary = path.with_suffix(".partial")
        checksum = hashlib.sha256()
        with (
            request(f"blobs/{descriptor['digest']}") as response,
            temporary.open("wb") as output,
        ):
            while data := response.read(1024 * 1024):
                checksum.update(data)
                output.write(data)
        if checksum.hexdigest() != name:
            raise RuntimeError("Blob checksum mismatch")
        temporary.replace(path)
    image_name = (repository.removeprefix("library/")) + ":" + tag
    (cache / "oci-layout").write_text(
        json.dumps({"imageLayoutVersion": "1.0.0"}), encoding="utf-8"
    )
    (cache / "index.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "manifests": [
                    {
                        "mediaType": manifest["mediaType"],
                        "digest": digest,
                        "size": len(raw),
                        "annotations": {
                            "io.containerd.image.name": "docker.io/" + image_name,
                            "org.opencontainers.image.ref.name": image_name,
                        },
                        "platform": {"os": "linux", "architecture": "amd64"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    archive = cache / "image.tar"
    with tarfile.open(archive, "w") as output:
        for name in ("oci-layout", "index.json"):
            output.add(cache / name, arcname=name)
        output.add(cache / "blobs", arcname="blobs")
    subprocess.run(
        ["docker", "load", "-i", str(archive), "--platform", "linux/amd64"], check=True
    )
    record = {
        "image": image_name,
        "registry_index_digest": root_digest,
        "platform_manifest_digest": digest,
        "config_digest": manifest["config"]["digest"],
    }
    (cache / "verified.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
