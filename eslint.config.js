import js from "@eslint/js";
import react from "eslint-plugin-react";
import globals from "globals";

const launchpadRules = {
    ...react.configs.recommended.rules,
    "react/prop-types": "off",
    "react/jsx-no-undef": ["error", { allowGlobals: true }],
    "no-empty": ["error", { allowEmptyCatch: true }],
    "no-unused-vars": ["error", {
        vars: "local",
        argsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
    }],
};

const launchpadLanguage = {
    ecmaVersion: 2022,
    sourceType: "script",
    parserOptions: {
        ecmaFeatures: { jsx: true },
    },
};

export default [
    js.configs.recommended,
    // provisioner.js and components.jsx — define their own globals, no cross-file refs needed
    {
        files: ["docs/launchpad/provisioner.js", "docs/launchpad/components.jsx"],
        plugins: { react },
        languageOptions: {
            ...launchpadLanguage,
            globals: {
                ...globals.browser,
                React: "readonly",
                ReactDOM: "readonly",
                AWS: "readonly",
            },
        },
        settings: { react: { version: "detect" } },
        rules: launchpadRules,
    },
    // app.jsx and data.js — consumers of components.jsx and provisioner.js globals
    {
        files: ["docs/launchpad/app.jsx", "docs/launchpad/data.js"],
        plugins: { react },
        languageOptions: {
            ...launchpadLanguage,
            globals: {
                ...globals.browser,
                React: "readonly",
                ReactDOM: "readonly",
                AWS: "readonly",
                // components.jsx exports
                SecretInput: "readonly",
                RegionSelect: "readonly",
                InstancePicker: "readonly",
                TerminalWindow: "readonly",
                DeployDetails: "readonly",
                HelpTip: "readonly",
                LiveTerminal: "readonly",
                SchedulerLogTerminal: "readonly",
                WorkerManagerTypeSelect: "readonly",
                // provisioner.js exports
                randomSuffix: "readonly",
                provision: "readonly",
                teardown: "readonly",
                downloadText: "readonly",
                buildConfigToml: "readonly",
            },
        },
        settings: { react: { version: "detect" } },
        rules: launchpadRules,
    },
];
