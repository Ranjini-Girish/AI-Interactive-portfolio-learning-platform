# CSV parsing library for gawk.
# Handles RFC 4180 quoted fields with embedded commas.
BEGIN {
    FPAT = "([^,]*)|(\"[^\"]*\")"
}
