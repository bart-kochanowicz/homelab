# 🏠 Homelab

This repo contains all of the configuration and documentation of my homelab.


## Introduction
A Kubernetes homelab setup using ArgoCD for GitOps. It uses [Talos Linux](https://www.talos.dev/) to set up machines.

## 💻 Hardware

- Lenovo ThinkCentre m720q i3-8100T/8GB/256GB
- Lenovo ThinkCentre m920q i5-8500T/32GB/512GB

## Software Requirements
- Kubernetes cluster (v1.25+)
- kubectl configured to access your cluster
- Git repository (GitHub, GitLab, or similar)

## TODO
- Self-hosted runner for CI/CD pipelines
- Self-hosted terraform state backend (MinIO + Terraform’s s3 backend)
- configure devcontainer environment

## Hosted Apps

- Home Assistant is deployed in-cluster and exposed through Cloudflare Tunnel.
- Crafty Controller is deployed in-cluster and exposed through Cloudflare Tunnel.
- n8n is deployed in-cluster and exposed through Cloudflare Tunnel with a protected editor at `n8n.thecavespace.com` and public webhooks at `n8n-webhook.thecavespace.com`.
