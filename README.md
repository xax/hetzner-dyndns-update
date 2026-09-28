# Hetzner ® DNS Dynamic Update Script

![Version: 1.1.0](https://img.shields.io/badge/version-1.1.0-blue.svg)
![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL%201.2-272398.svg?logo=europeanunion)

A bash script to update A, AAAA, and CNAME DNS resource records for specified domains using the Hetzner® Cloud API.

## Overview

This script updates DNS records on Hetzner Cloud to your public IP address. It supports:

- **A records** - IPv4 addresses
- **AAAA records** - IPv6 addresses
- **CNAME records** - domain aliases

The script fetches your current public IP addresses, compares them with existing DNS records, and updates them if they differ.

To make this script update the resource records whenever your public IP changes, make it run as aCRON job or find another
trigger to run it on IP changes.

## Features

- ✅ Update A records with current IPv4 address
- ✅ Update AAAA records with current IPv6 address (if available)
- ✅ Update CNAME records to point to target domains
- ✅ Graceful handling when records are already up to date
- ✅ Configurable TTL for DNS records
- ✅ Support for multiple domains and CNAME mappings

## Prerequisites

- [Hetzner® Cloud API key](https://hetzner.cloud/console/api) with DNS zone read/write permissions
- `curl` and `jq` installed on the system

## Configuration

Edit `dyndns-hetzner.sh` and set the following variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `HETZNER_API_KEY` | Your Hetzner Cloud API key | `"kuhgKKJGBZREASH34zfgjhdcfg6t6fdO3kjbdsf6Tb4HDC6HsdfGsKOKjgcf52BJ"` |
| `HETZNER_API_URL` | Hetzner Cloud API endpoint | `"https://api.hetzner.cloud/v1"` |
| `HETZNER_TTL` | TTL value for DNS records in seconds | `60` |
| `DOMAINS` | Array of domains to update A/AAAA records for | `("domain.example" "www.domain.example")` |
| `CNAME_RECORDS` | Associative array mapping subdomains to target domains | `([\"www.domain.tld\"]=\"domain.tld\")` |

## Usage

```bash
# Make the script executable
chmod +x dyndns-hetzner.sh

# Run the script
./dyndns-hetzner.sh
```

The script will:
1. Fetch your current public IPv4 and IPv6 addresses
2. For each domain in the `DOMAINS` array:
   - Update the A record if the IPv4 address has changed
   - Update the AAAA record if the IPv6 address has changed (and is available)
3. For each CNAME mapping:
   - Update the CNAME record if the target has changed

## How It Works

1. **IP Detection**: The script fetches current public IP addresses using `icanhazip.com`
2. **Zone Lookup**: It queries Hetzner Cloud API to find the zone ID for each domain's main domain
3. **Record Comparison**: Existing DNS records are compared with the current IP addresses
4. **Record Update**: If records differ, they are removed and re-added with the new values
5. **CNAME Support**: Special handling for CNAME records mapping subdomains to target domains

## Configuration Details

### Domains Array

```bash
DOMAINS=(
    "domain.example"
    "www.domain.example"
)
```

Each domain is processed to extract the subdomain prefix. For example:
- `domain.example` → subdomain `@`
- `www.domain.example` → subdomain `www`

### CNAME Mappings

```bash
declare -A CNAME_RECORDS=(
    ["www.domain.tld"]="domain.tld"
)
```

This maps `www.domain.tld` to point to `domain.tld` via a CNAME record.

## License

This project is licensed under the *European Union Public Licence* version 1.2. See the LICENSE file for more details.

## Version

1.0.0 - Initial release supporting A, AAAA, and CNAME DNS record updates via Hetzner Cloud API.
1.1.0 - Remove entire A/AAAA resource records; bug fixes (ttl should be numerical).
