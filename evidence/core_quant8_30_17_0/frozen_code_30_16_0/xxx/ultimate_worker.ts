import { parentPort, workerData } from "node:worker_threads";
import { runStudy } from "./ultimate_replay";
if (parentPort) {
  try {
    parentPort.postMessage({
      report: runStudy(
        workerData.protocol,
        workerData.data,
        workerData.registeredAt,
        workerData.limits,
      ),
    });
  } catch (e) {
    parentPort.postMessage({
      error: e instanceof Error ? e.message : String(e),
    });
  }
}
