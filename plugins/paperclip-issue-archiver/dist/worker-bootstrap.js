import { startWorkerRpcHost } from "@paperclipai/plugin-sdk";
import worker from "./worker.js";

startWorkerRpcHost({ plugin: worker });
