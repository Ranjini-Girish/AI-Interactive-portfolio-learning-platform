#include <iostream>
#include <string>
#include "json.h"
#include "linker/types.h"
#include "linker/loader.h"
#include "linker/resolver.h"
#include "linker/relocator.h"
#include "linker/reporter.h"

int main(int argc, char* argv[]) {
    std::string cfg_path = "/app/data/link_config.json";
    std::string out_path = "/app/output/link_report.json";
    if (argc >= 2) cfg_path = argv[1];
    if (argc >= 3) out_path = argv[2];

    // TODO: load config, load objects, resolve, relocate, write report
    std::cerr << "linker: not yet implemented" << std::endl;
    return 1;
}
