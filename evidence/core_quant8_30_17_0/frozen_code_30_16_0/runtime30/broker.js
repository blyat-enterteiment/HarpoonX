"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.alpaca = alpaca;
exports.normalizeOrder = normalizeOrder;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const node_vm_1 = __importDefault(require("node:vm"));
const validators_1 = require("./validators");
/** Reuse the audited priority/rate-limited transport. Its market and trading queues are separate. */
function alpaca(key, secret) {
    if (!key || !secret)
        throw Error("Alpaca PAPER credentials required");
    const ctx = node_vm_1.default.createContext({
        fetch,
        URL,
        URLSearchParams,
        AbortController,
        setTimeout,
        clearTimeout,
        Date,
        Math,
        JSON,
        Number,
        Error,
        console,
    });
    node_vm_1.default.runInContext(node_fs_1.default.readFileSync(node_path_1.default.join(__dirname, "../src/io.js"), "utf8"), ctx);
    ctx.credentials = { key, secret };
    return node_vm_1.default.runInContext("new DirectAlpaca('paper',credentials)", ctx);
}
function normalizeOrder(o, clientId) {
    return (0, validators_1.assertOrder)(o, clientId);
}
