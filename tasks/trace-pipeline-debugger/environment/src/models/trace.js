'use strict';

function buildTree(spans) {
    const spanMap = {};
    let root = null;

    for (const span of spans) {
        spanMap[span.span_id] = { ...span, children: [] };
    }

    for (const span of spans) {
        if (span.parent_span_id && spanMap[span.parent_span_id]) {
            spanMap[span.parent_span_id].children.push(spanMap[span.span_id]);
        } else if (!span.parent_span_id) {
            root = spanMap[span.span_id];
        }
    }

    return root;
}

function depth(node) {
    if (!node || !node.children || node.children.length === 0) return 1;
    return 1 + Math.max(...node.children.map(depth));
}

module.exports = { buildTree, depth };
