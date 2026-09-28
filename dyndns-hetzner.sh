#!/bin/bash

# SPDX-FileCopyrightText: Copyright (C) Sep 2026 XA. All rights reserved.
# SPDX-License-Identifier: EUPL-1.2
# Version: 1.1.0
#
# Updates A, AAAA DNS resource records for specified domains/hosts and CNAMEs
# using the Hetzner Cloud API (as of in place at 2026):
# »  https://docs.hetzner.cloud/reference/cloud

set -euo pipefail

# Hetzner API key
HETZNER_API_KEY=""
HETZNER_API_URL="https://api.hetzner.cloud/v1"
HETZNER_TTL=60

# Domains with A/AAAA records
DOMAINS=(
    "domain.example"
    "www.domain.example"
)

# CNAME mappings
declare -A CNAME_RECORDS=(
    ["www.domain.tld"]="domain.tld"
)

cName="${0##*/}"
cSelfPath="$(realpath -LP "${0%$cName}" )"
cSelfPath="${cSelfPath:-.}/"

if [[ -r "${cSelfPath}${cName%.*}.conf" ]]; then
   source ${cSelfPath}${cName%.*}.conf
fi

# current public IP addresses
CURRENT_IPV4="$(curl -s https://ipv4.icanhazip.com)"
CURRENT_IPV6="$(curl -s --max-time 5 https://ipv6.icanhazip.com || true)"

# delete a dns resource record set
delete_rrset() {
    local ZONE_ID="$1"
    local SUBDOMAIN="$2"
    local RECORD_TYPE="$3"
    echo "🗑 Deleting record set type: $RECORD_TYPE"
    curl -s -X DELETE "$HETZNER_API_URL/zones/$ZONE_ID/rrsets/$SUBDOMAIN/$RECORD_TYPE" \
        -H "Authorization: Bearer $HETZNER_API_KEY" \
    > /dev/null
}

# delete a dns resource record
delete_record() {
    local ZONE_ID="$1"
    local SUBDOMAIN="$2"
    local RECORD_ID="$3"
    local RECORD_VALUE="$4"
    if [[ -n "$RECORD_ID" && "$RECORD_ID" != "null" ]]; then
        echo "🗑 Deleting record: $RECORD_ID"
        curl -s -X POST "$HETZNER_API_URL/zones/$ZONE_ID/rrsets/$SUBDOMAIN/$RECORD_ID/actions/remove_records" \
            -H "Authorization: Bearer $HETZNER_API_KEY" \
            -d "{
                \"records\": [
                    \"value\": \"$RECORD_VALUE\"
                ]
            }" > /dev/null
    fi
}

# update an A or AAAA resource record
update_domain() {
    local DOMAIN="$1"
    local MAIN_DOMAIN="$(echo "$DOMAIN" | awk -F'.' '{print $(NF-1)"."$NF}')"
    local SUBDOMAIN="${DOMAIN/.$MAIN_DOMAIN/}"
    [[ "$SUBDOMAIN" == "$DOMAIN" ]] && SUBDOMAIN="@"

    local ZONE_ID="$(curl -s -H "Authorization: Bearer $HETZNER_API_KEY" "$HETZNER_API_URL/zones" |
        jq -r ".zones[] | select(.name==\"$MAIN_DOMAIN\") | .id")"

    if [[ -z "$ZONE_ID" ]]; then
        echo "❌ Unable to find zone for ${DOMAIN}!"
        return
    fi

    local RECORDS="$(curl -s -H "Authorization: Bearer $HETZNER_API_KEY" "$HETZNER_API_URL/zones/$ZONE_ID/rrsets")"

    # check A record
    local RECORD_A="$(echo "$RECORDS" | jq -r ".rrsets[] | select(.name==\"$SUBDOMAIN\" and .type==\"A\")")"
    local EXISTING_IPV4="$(echo "$RECORD_A" | jq -r ".records[0].value")"
    local RECORD_ID_A="$(echo "$RECORD_A" | jq -r ".id")"

    if [[ "$EXISTING_IPV4" != "$CURRENT_IPV4" ]]; then
        delete_rrset "$ZONE_ID" "$SUBDOMAIN" A
        # delete_record "$ZONE_ID" "$SUBDOMAIN" "$RECORD_ID_A" "$EXISTING_IPV4"
        echo "[$DOMAIN] ➡️ Setting new A record to $CURRENT_IPV4"
        curl -s -X POST "$HETZNER_API_URL/zones/$ZONE_ID/rrsets/$SUBDOMAIN/A/actions/add_records" \
            -H "Authorization: Bearer $HETZNER_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{
                \"ttl\": $HETZNER_TTL,
                \"records\": [
                    {
                        \"value\": \"$CURRENT_IPV4\"
                    }
                ]
            }" > /dev/null
    else
        echo "[$DOMAIN] ✅ A record already up to date ($CURRENT_IPV4)"
    fi

    # check AAAA record
    if [[ -n "$CURRENT_IPV6" ]]; then
        local RECORD_AAAA="$(echo "$RECORDS" | jq -r ".rrsets[] | select(.name==\"$SUBDOMAIN\" and .type==\"AAAA\")")"
        local EXISTING_IPV6="$(echo "$RECORD_AAAA" | jq -r ".records[0].value")"
        local RECORD_ID_AAAA="$(echo "$RECORD_AAAA" | jq -r ".id")"

        if [[ "$EXISTING_IPV6" != "$CURRENT_IPV6" ]]; then
            delete_rrset "$ZONE_ID" "$SUBDOMAIN" AAAA
            # delete_record "$ZONE_ID" "$SUBDOMAIN" "$RECORD_ID_AAAA" "$EXISTING_IPV6"
            echo "[$DOMAIN] ➡️ Setting new AAAA record to $CURRENT_IPV6"
            curl -s -X POST "$HETZNER_API_URL/zones/$ZONE_ID/rrsets/$SUBDOMAIN/AAAA/actions/update_records" \
                -H "Authorization: Bearer $HETZNER_API_KEY" \
                -H "Content-Type: application/json" \
                -d "{
                    \"ttl\": $HETZNER_TTL,
                    \"records\": [
                        {
                            \"value\": \"$CURRENT_IPV6\"
                        }
                    ]
                }" > /dev/null
        else
            echo "[$DOMAIN] ✅ AAAA record already up to date ($CURRENT_IPV6)"
        fi
    fi
}

# update a CNAME resource record
update_cname() {
    local SUBDOMAIN="$1"
    local TARGET="$2"
    local MAIN_DOMAIN="$(echo "$SUBDOMAIN" | awk -F'.' '{print $(NF-1)"."$NF}')"

    local ZONE_ID="$(curl -s -H "Authorization: Bearer $HETZNER_API_KEY" "$HETZNER_API_URL/zones" |
        jq -r ".zones[] | select(.name==\"$MAIN_DOMAIN\") | .id")"

    if [[ -z "$ZONE_ID" ]]; then
        echo "❌ Unable to find zone for ${MAIN_DOMAIN}!"
        return
    fi

    local RECORDS="$(curl -s -H "Authorization: Bearer $HETZNER_API_KEY" "$HETZNER_API_URL/zones/$ZONE_ID/rrsets")"
    local RECORD="$(echo "$RECORDS" | jq -r ".rrsets[] | select(.name==\"$SUBDOMAIN\" and .type==\"CNAME\")")"
    local EXISTING_TARGET=$(echo "$RECORD" | jq -r ".value")
    local RECORD_ID=$(echo "$RECORD" | jq -r ".id")

    if [[ "$EXISTING_TARGET" != "$TARGET" ]]; then
        delete_record "$ZONE_ID" "$SUB_DOMAIN" "$RECORD_ID" "$EXISTING_TARGET"
        echo "[$SUBDOMAIN] ➡️ Setting new CNAME record to $TARGET"
        curl -s -X POST "$HETZNER_API_URL/zones/$ZONE_ID/rrsets/$SUBDOMAIN/CNAME/actions/add_records" \
            -H "Authentication: Bearer $HETZNER_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{
                \"ttl\": $HETZNER_TTL,
                \"records\": [
                    {
                        \"value\": \"$TARGET\"
                    }
                ]
            }" > /dev/null
    else
        echo "[$SUBDOMAIN] ✅ CNAME already up to date ($TARGET)"
    fi
}

# Run
echo "🌐 Starting DNS update…"

for DOMAIN in "${DOMAINS[@]}"; do
    if [[ -n "${CNAME_RECORDS[$DOMAIN]:-}" ]]; then
        update_cname "$DOMAIN" "${CNAME_RECORDS[$DOMAIN]}"
    else
        update_domain "$DOMAIN"
    fi
done

echo "✅ DNS update completed."
