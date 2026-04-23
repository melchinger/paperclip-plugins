import { definePlugin } from "@paperclipai/plugin-sdk";

var plugin = definePlugin({
  async setup(ctx) {
    ctx.logger.info("Paperclip Issue Archiver worker ready");
  },
  async onHealth() {
    return {
      status: "ok",
      message: "Paperclip Issue Archiver worker is running"
    };
  }
});

var worker_default = plugin;
export {
  worker_default as default
};
