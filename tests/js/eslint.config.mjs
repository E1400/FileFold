// Only one rule matters here: a reference to a name that is never declared is a
// guaranteed runtime ReferenceError (this is how a deleted NON_EXTRACTABLE constant
// broke the whole create-workspace flow).
export default [{
  files: ["**/*.js"],
  languageOptions: {
    ecmaVersion: 2023,
    sourceType: "script",
    globals: {
      window: "readonly", document: "readonly", console: "readonly", fetch: "readonly",
      FormData: "readonly", URL: "readonly", Blob: "readonly", localStorage: "readonly",
      setTimeout: "readonly", clearTimeout: "readonly", setInterval: "readonly",
      clearInterval: "readonly", requestAnimationFrame: "readonly", navigator: "readonly",
      Proxy: "readonly", CSS: "readonly",
      matchMedia: "readonly", alert: "readonly", confirm: "readonly", location: "readonly",
      history: "readonly", getComputedStyle: "readonly", Event: "readonly",
      MutationObserver: "readonly", ResizeObserver: "readonly", AbortController: "readonly",
    },
  },
  rules: { "no-undef": "error" },
}];
