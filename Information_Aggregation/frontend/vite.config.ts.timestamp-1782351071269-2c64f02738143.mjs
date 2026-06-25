// vite.config.ts
import { defineConfig, loadEnv } from "file:///D:/AI/xling_ai_system/Information_Aggregation/frontend/node_modules/vite/dist/node/index.js";
import vue from "file:///D:/AI/xling_ai_system/Information_Aggregation/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import basicSsl from "file:///D:/AI/xling_ai_system/Information_Aggregation/frontend/node_modules/@vitejs/plugin-basic-ssl/dist/index.mjs";
import { fileURLToPath, URL } from "node:url";
var __vite_injected_original_import_meta_url = "file:///D:/AI/xling_ai_system/Information_Aggregation/frontend/vite.config.ts";
var vite_config_default = defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devHttps = env.VITE_DEV_HTTPS === "true";
  const influencerApiTarget = env.VITE_INFLUENCER_API_TARGET || env.VITE_API_TARGET || "http://127.0.0.1:8000";
  const meetingApiTarget = env.VITE_MEETING_API_TARGET || "http://127.0.0.1:8001";
  const flybookApiTarget = env.VITE_FLYBOOK_API_TARGET || "http://127.0.0.1:8002";
  const meetingApiPrefixes = [
    "/api/auth",
    "/api/meeting",
    "/api/meetings",
    "/api/notifications",
    "/api/ws",
    "/api/admin",
    "/api/export",
    "/api/settings"
  ];
  const proxy = {
    "/api/v1": {
      target: influencerApiTarget,
      changeOrigin: true
    },
    "/api/flybook": {
      target: flybookApiTarget,
      changeOrigin: true,
      ws: true
    },
    "/meeting-app": {
      target: meetingApiTarget,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/meeting-app/, "") || "/"
    },
    "/static": {
      target: meetingApiTarget,
      changeOrigin: true
    }
  };
  for (const prefix of meetingApiPrefixes) {
    proxy[prefix] = {
      target: meetingApiTarget,
      changeOrigin: true,
      ws: prefix === "/api/ws"
    };
  }
  return {
    plugins: [vue(), ...devHttps ? [basicSsl()] : []],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", __vite_injected_original_import_meta_url))
      }
    },
    server: {
      host: "0.0.0.0",
      port: Number(env.VITE_DEV_PORT || 5173),
      strictPort: true,
      allowedHosts: true,
      proxy
    },
    preview: {
      host: "0.0.0.0",
      port: Number(env.VITE_PREVIEW_PORT || 4173),
      allowedHosts: true,
      proxy
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "element-plus": ["element-plus"],
            "vue-vendor": ["vue", "vue-router", "pinia"]
          }
        }
      }
    }
  };
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcudHMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCJEOlxcXFxBSVxcXFx4bGluZ19haV9zeXN0ZW1cXFxcSW5mb3JtYXRpb25fQWdncmVnYXRpb25cXFxcZnJvbnRlbmRcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkQ6XFxcXEFJXFxcXHhsaW5nX2FpX3N5c3RlbVxcXFxJbmZvcm1hdGlvbl9BZ2dyZWdhdGlvblxcXFxmcm9udGVuZFxcXFx2aXRlLmNvbmZpZy50c1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRDovQUkveGxpbmdfYWlfc3lzdGVtL0luZm9ybWF0aW9uX0FnZ3JlZ2F0aW9uL2Zyb250ZW5kL3ZpdGUuY29uZmlnLnRzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnLCBsb2FkRW52IH0gZnJvbSAndml0ZSdcclxuaW1wb3J0IHZ1ZSBmcm9tICdAdml0ZWpzL3BsdWdpbi12dWUnXHJcbmltcG9ydCBiYXNpY1NzbCBmcm9tICdAdml0ZWpzL3BsdWdpbi1iYXNpYy1zc2wnXHJcbmltcG9ydCB7IGZpbGVVUkxUb1BhdGgsIFVSTCB9IGZyb20gJ25vZGU6dXJsJ1xyXG5cclxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKCh7IG1vZGUgfSkgPT4ge1xyXG4gIGNvbnN0IGVudiA9IGxvYWRFbnYobW9kZSwgcHJvY2Vzcy5jd2QoKSwgJycpXHJcbiAgY29uc3QgZGV2SHR0cHMgPSBlbnYuVklURV9ERVZfSFRUUFMgPT09ICd0cnVlJ1xyXG4gIGNvbnN0IGluZmx1ZW5jZXJBcGlUYXJnZXQgPSBlbnYuVklURV9JTkZMVUVOQ0VSX0FQSV9UQVJHRVQgfHwgZW52LlZJVEVfQVBJX1RBUkdFVCB8fCAnaHR0cDovLzEyNy4wLjAuMTo4MDAwJ1xyXG4gIGNvbnN0IG1lZXRpbmdBcGlUYXJnZXQgPSBlbnYuVklURV9NRUVUSU5HX0FQSV9UQVJHRVQgfHwgJ2h0dHA6Ly8xMjcuMC4wLjE6ODAwMSdcclxuICBjb25zdCBmbHlib29rQXBpVGFyZ2V0ID0gZW52LlZJVEVfRkxZQk9PS19BUElfVEFSR0VUIHx8ICdodHRwOi8vMTI3LjAuMC4xOjgwMDInXHJcblxyXG4gIGNvbnN0IG1lZXRpbmdBcGlQcmVmaXhlcyA9IFtcclxuICAgICcvYXBpL2F1dGgnLFxyXG4gICAgJy9hcGkvbWVldGluZycsXHJcbiAgICAnL2FwaS9tZWV0aW5ncycsXHJcbiAgICAnL2FwaS9ub3RpZmljYXRpb25zJyxcclxuICAgICcvYXBpL3dzJyxcclxuICAgICcvYXBpL2FkbWluJyxcclxuICAgICcvYXBpL2V4cG9ydCcsXHJcbiAgICAnL2FwaS9zZXR0aW5ncycsXHJcbiAgXVxyXG5cclxuICBjb25zdCBwcm94eTogUmVjb3JkPHN0cmluZywgb2JqZWN0PiA9IHtcclxuICAgICcvYXBpL3YxJzoge1xyXG4gICAgICB0YXJnZXQ6IGluZmx1ZW5jZXJBcGlUYXJnZXQsXHJcbiAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcclxuICAgIH0sXHJcbiAgICAnL2FwaS9mbHlib29rJzoge1xyXG4gICAgICB0YXJnZXQ6IGZseWJvb2tBcGlUYXJnZXQsXHJcbiAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcclxuICAgICAgd3M6IHRydWUsXHJcbiAgICB9LFxyXG4gICAgJy9tZWV0aW5nLWFwcCc6IHtcclxuICAgICAgdGFyZ2V0OiBtZWV0aW5nQXBpVGFyZ2V0LFxyXG4gICAgICBjaGFuZ2VPcmlnaW46IHRydWUsXHJcbiAgICAgIHJld3JpdGU6IChwYXRoOiBzdHJpbmcpID0+IHBhdGgucmVwbGFjZSgvXlxcL21lZXRpbmctYXBwLywgJycpIHx8ICcvJyxcclxuICAgIH0sXHJcbiAgICAnL3N0YXRpYyc6IHtcclxuICAgICAgdGFyZ2V0OiBtZWV0aW5nQXBpVGFyZ2V0LFxyXG4gICAgICBjaGFuZ2VPcmlnaW46IHRydWUsXHJcbiAgICB9LFxyXG4gIH1cclxuXHJcbiAgZm9yIChjb25zdCBwcmVmaXggb2YgbWVldGluZ0FwaVByZWZpeGVzKSB7XHJcbiAgICBwcm94eVtwcmVmaXhdID0ge1xyXG4gICAgICB0YXJnZXQ6IG1lZXRpbmdBcGlUYXJnZXQsXHJcbiAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcclxuICAgICAgd3M6IHByZWZpeCA9PT0gJy9hcGkvd3MnLFxyXG4gICAgfVxyXG4gIH1cclxuXHJcbiAgcmV0dXJuIHtcclxuICAgIHBsdWdpbnM6IFt2dWUoKSwgLi4uKGRldkh0dHBzID8gW2Jhc2ljU3NsKCldIDogW10pXSxcclxuICAgIHJlc29sdmU6IHtcclxuICAgICAgYWxpYXM6IHtcclxuICAgICAgICAnQCc6IGZpbGVVUkxUb1BhdGgobmV3IFVSTCgnLi9zcmMnLCBpbXBvcnQubWV0YS51cmwpKSxcclxuICAgICAgfSxcclxuICAgIH0sXHJcbiAgICBzZXJ2ZXI6IHtcclxuICAgICAgaG9zdDogJzAuMC4wLjAnLFxyXG4gICAgICBwb3J0OiBOdW1iZXIoZW52LlZJVEVfREVWX1BPUlQgfHwgNTE3MyksXHJcbiAgICAgIHN0cmljdFBvcnQ6IHRydWUsXHJcbiAgICAgIGFsbG93ZWRIb3N0czogdHJ1ZSxcclxuICAgICAgcHJveHksXHJcbiAgICB9LFxyXG4gICAgcHJldmlldzoge1xyXG4gICAgICBob3N0OiAnMC4wLjAuMCcsXHJcbiAgICAgIHBvcnQ6IE51bWJlcihlbnYuVklURV9QUkVWSUVXX1BPUlQgfHwgNDE3MyksXHJcbiAgICAgIGFsbG93ZWRIb3N0czogdHJ1ZSxcclxuICAgICAgcHJveHksXHJcbiAgICB9LFxyXG4gICAgYnVpbGQ6IHtcclxuICAgICAgcm9sbHVwT3B0aW9uczoge1xyXG4gICAgICAgIG91dHB1dDoge1xyXG4gICAgICAgICAgbWFudWFsQ2h1bmtzOiB7XHJcbiAgICAgICAgICAgICdlbGVtZW50LXBsdXMnOiBbJ2VsZW1lbnQtcGx1cyddLFxyXG4gICAgICAgICAgICAndnVlLXZlbmRvcic6IFsndnVlJywgJ3Z1ZS1yb3V0ZXInLCAncGluaWEnXSxcclxuICAgICAgICAgIH0sXHJcbiAgICAgICAgfSxcclxuICAgICAgfSxcclxuICAgIH0sXHJcbiAgfVxyXG59KVxyXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQThWLFNBQVMsY0FBYyxlQUFlO0FBQ3BZLE9BQU8sU0FBUztBQUNoQixPQUFPLGNBQWM7QUFDckIsU0FBUyxlQUFlLFdBQVc7QUFIMEwsSUFBTSwyQ0FBMkM7QUFLOVEsSUFBTyxzQkFBUSxhQUFhLENBQUMsRUFBRSxLQUFLLE1BQU07QUFDeEMsUUFBTSxNQUFNLFFBQVEsTUFBTSxRQUFRLElBQUksR0FBRyxFQUFFO0FBQzNDLFFBQU0sV0FBVyxJQUFJLG1CQUFtQjtBQUN4QyxRQUFNLHNCQUFzQixJQUFJLDhCQUE4QixJQUFJLG1CQUFtQjtBQUNyRixRQUFNLG1CQUFtQixJQUFJLDJCQUEyQjtBQUN4RCxRQUFNLG1CQUFtQixJQUFJLDJCQUEyQjtBQUV4RCxRQUFNLHFCQUFxQjtBQUFBLElBQ3pCO0FBQUEsSUFDQTtBQUFBLElBQ0E7QUFBQSxJQUNBO0FBQUEsSUFDQTtBQUFBLElBQ0E7QUFBQSxJQUNBO0FBQUEsSUFDQTtBQUFBLEVBQ0Y7QUFFQSxRQUFNLFFBQWdDO0FBQUEsSUFDcEMsV0FBVztBQUFBLE1BQ1QsUUFBUTtBQUFBLE1BQ1IsY0FBYztBQUFBLElBQ2hCO0FBQUEsSUFDQSxnQkFBZ0I7QUFBQSxNQUNkLFFBQVE7QUFBQSxNQUNSLGNBQWM7QUFBQSxNQUNkLElBQUk7QUFBQSxJQUNOO0FBQUEsSUFDQSxnQkFBZ0I7QUFBQSxNQUNkLFFBQVE7QUFBQSxNQUNSLGNBQWM7QUFBQSxNQUNkLFNBQVMsQ0FBQyxTQUFpQixLQUFLLFFBQVEsa0JBQWtCLEVBQUUsS0FBSztBQUFBLElBQ25FO0FBQUEsSUFDQSxXQUFXO0FBQUEsTUFDVCxRQUFRO0FBQUEsTUFDUixjQUFjO0FBQUEsSUFDaEI7QUFBQSxFQUNGO0FBRUEsYUFBVyxVQUFVLG9CQUFvQjtBQUN2QyxVQUFNLE1BQU0sSUFBSTtBQUFBLE1BQ2QsUUFBUTtBQUFBLE1BQ1IsY0FBYztBQUFBLE1BQ2QsSUFBSSxXQUFXO0FBQUEsSUFDakI7QUFBQSxFQUNGO0FBRUEsU0FBTztBQUFBLElBQ0wsU0FBUyxDQUFDLElBQUksR0FBRyxHQUFJLFdBQVcsQ0FBQyxTQUFTLENBQUMsSUFBSSxDQUFDLENBQUU7QUFBQSxJQUNsRCxTQUFTO0FBQUEsTUFDUCxPQUFPO0FBQUEsUUFDTCxLQUFLLGNBQWMsSUFBSSxJQUFJLFNBQVMsd0NBQWUsQ0FBQztBQUFBLE1BQ3REO0FBQUEsSUFDRjtBQUFBLElBQ0EsUUFBUTtBQUFBLE1BQ04sTUFBTTtBQUFBLE1BQ04sTUFBTSxPQUFPLElBQUksaUJBQWlCLElBQUk7QUFBQSxNQUN0QyxZQUFZO0FBQUEsTUFDWixjQUFjO0FBQUEsTUFDZDtBQUFBLElBQ0Y7QUFBQSxJQUNBLFNBQVM7QUFBQSxNQUNQLE1BQU07QUFBQSxNQUNOLE1BQU0sT0FBTyxJQUFJLHFCQUFxQixJQUFJO0FBQUEsTUFDMUMsY0FBYztBQUFBLE1BQ2Q7QUFBQSxJQUNGO0FBQUEsSUFDQSxPQUFPO0FBQUEsTUFDTCxlQUFlO0FBQUEsUUFDYixRQUFRO0FBQUEsVUFDTixjQUFjO0FBQUEsWUFDWixnQkFBZ0IsQ0FBQyxjQUFjO0FBQUEsWUFDL0IsY0FBYyxDQUFDLE9BQU8sY0FBYyxPQUFPO0FBQUEsVUFDN0M7QUFBQSxRQUNGO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
