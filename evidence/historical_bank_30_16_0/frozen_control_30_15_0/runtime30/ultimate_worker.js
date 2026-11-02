"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const node_worker_threads_1 = require("node:worker_threads");
const ultimate_replay_1 = require("./ultimate_replay");
if (node_worker_threads_1.parentPort) {
    try {
        node_worker_threads_1.parentPort.postMessage({
            report: (0, ultimate_replay_1.runStudy)(node_worker_threads_1.workerData.protocol, node_worker_threads_1.workerData.data, node_worker_threads_1.workerData.registeredAt, node_worker_threads_1.workerData.limits),
        });
    }
    catch (e) {
        node_worker_threads_1.parentPort.postMessage({
            error: e instanceof Error ? e.message : String(e),
        });
    }
}
