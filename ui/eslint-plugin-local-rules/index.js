/**
 * Local ESLint plugin — project-specific rules that don't warrant a
 * published npm package.
 *
 * Wire into .eslintrc.json:
 *   "plugins": ["local-rules"]
 *   "rules": { "local-rules/no-semantic-dark-overrides": "warn" }
 */
module.exports = {
  rules: {
    'no-semantic-dark-overrides': require('../eslint-rules/no-semantic-dark-overrides'),
  },
}
