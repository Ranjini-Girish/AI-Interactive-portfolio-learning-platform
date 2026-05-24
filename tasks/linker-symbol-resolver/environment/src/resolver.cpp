#include "linker/resolver.h"
#include <algorithm>
#include <set>

ResolveResult resolve(const std::vector<ObjectFile>& /*objects*/, const LinkConfig& /*config*/) {
    // TODO: merge sections with alignment, resolve symbols (GLOBAL > WEAK)
    return {};
}
