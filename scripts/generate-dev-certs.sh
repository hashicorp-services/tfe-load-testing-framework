#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cert_dir="${repo_root}/platform/tfe/certs"
hostname="${1:-tfe.localdemo.me}"
tmp_dir="$(mktemp -d)"

cleanup() {
  rm -rf "${tmp_dir}"
}

trap cleanup EXIT

mkdir -p "${cert_dir}"

cat >"${tmp_dir}/server-cert.cnf" <<EOF
[req]
distinguished_name = req_distinguished_name
prompt = no
req_extensions = req_ext

[req_distinguished_name]
CN = ${hostname}

[req_ext]
subjectAltName = DNS:${hostname}
EOF

cat >"${tmp_dir}/ca-cert.cnf" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca
prompt = no

[req_distinguished_name]
CN = ${hostname} Demo CA

[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
EOF

openssl req \
  -x509 \
  -newkey rsa:4096 \
  -sha256 \
  -days 3650 \
  -nodes \
  -keyout "${cert_dir}/ca-key.pem" \
  -out "${cert_dir}/ca.pem" \
  -config "${tmp_dir}/ca-cert.cnf"

openssl req \
  -newkey rsa:4096 \
  -sha256 \
  -nodes \
  -keyout "${cert_dir}/key.pem" \
  -out "${tmp_dir}/cert.csr" \
  -config "${tmp_dir}/server-cert.cnf"

openssl x509 \
  -req \
  -in "${tmp_dir}/cert.csr" \
  -CA "${cert_dir}/ca.pem" \
  -CAkey "${cert_dir}/ca-key.pem" \
  -CAcreateserial \
  -CAserial "${tmp_dir}/ca.srl" \
  -out "${cert_dir}/cert.pem" \
  -days 825 \
  -sha256 \
  -extfile "${tmp_dir}/server-cert.cnf" \
  -extensions req_ext

cat "${cert_dir}/cert.pem" "${cert_dir}/ca.pem" >"${cert_dir}/bundle.pem"
chmod 600 "${cert_dir}/key.pem" "${cert_dir}/ca-key.pem"

printf 'generated development certificates for %s in %s\n' "${hostname}" "${cert_dir}"
printf 'trust the demo CA from %s/ca.pem, or use curl --cacert %s/ca.pem https://%s\n' "${cert_dir}" "${cert_dir}" "${hostname}"
