package k8sdetect

import (
	"os"
	"path/filepath"
	"testing"
)

const k3sKubeconfig = `apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: Zm FrZQ==
    server: https://127.0.0.1:6443
  name: default
users:
- name: default
  user:
    client-certificate-data: eA==
`

func TestDetectK3s(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "etc/rancher/k3s/k3s.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(k3sKubeconfig), 0o600); err != nil {
		t.Fatal(err)
	}

	detection := Detect(root)
	if detection == nil {
		t.Fatal("k3s not detected")
	}
	if detection.Distro != "k3s" || detection.APIEndpoint != "https://127.0.0.1:6443" {
		t.Fatalf("detection wrong: %+v", detection)
	}
	if detection.Kubeconfig == "" || detection.Hash == "" {
		t.Fatal("kubeconfig content / hash missing")
	}

	// Hash is stable while nothing changes, and changes with content.
	again := Detect(root)
	if again.Hash != detection.Hash {
		t.Fatal("hash not stable")
	}
	_ = os.WriteFile(path, []byte(k3sKubeconfig+"# changed\n"), 0o600)
	if Detect(root).Hash == detection.Hash {
		t.Fatal("hash did not change with content")
	}
}

func TestDetectNothing(t *testing.T) {
	if Detect(t.TempDir()) != nil {
		t.Fatal("false positive on empty root")
	}
}
