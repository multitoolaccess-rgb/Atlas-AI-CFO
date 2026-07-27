/**
 * @fileoverview Disallow dark: overrides on semantic color tokens.
 *
 * The design system's semantic CSS variables (--danger-*, --warning-*,
 * --success-*, --info-*, --primary-*) already invert in dark mode via
 * tokens.css. Adding dark:bg-danger-*, dark:text-warning-*, etc. fights
 * the token system and produces washed-out or invisible results.
 *
 * Use the semantic token without a dark: prefix — it adapts automatically.
 *
 * BAD:   className="text-danger-600 dark:text-danger-400"
 * GOOD:  className="text-danger-600"
 * BAD:   className="bg-warning-50 dark:bg-warning-900/20"
 * GOOD:  className="bg-warning-50"
 */

/** @type {import('eslint').Rule.RuleModule} */
module.exports = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Disallow dark: overrides on semantic color tokens (warning, danger, success, info, primary). These tokens already invert via tokens.css.',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      redundantDarkOverride:
        'Remove `{{token}}` — semantic CSS variables already invert in dark mode via tokens.css. The dark: override fights the token system.',
    },
    schema: [],
  },

  create(context) {
    // Matches dark: prefix + (bg|text|border|ring|outline|from|to|via|divide|placeholder|accent|caret|decoration|shadow)
    // + semantic color name + optional scale number and optional opacity modifier.
    // Examples matched:
    //   dark:text-danger-400
    //   dark:bg-warning-900/20
    //   dark:border-info-700
    //   dark:text-success-400
    //   dark:bg-primary-500/10
    const PATTERN = /dark:(?:bg|text|border|ring|outline|from|to|via|divide|placeholder|accent|caret|decoration|shadow|hover:bg|hover:text|hover:border|focus:bg|focus:text|focus:border)-(?:warning|danger|success|info|primary)-\d+(?:\/\d+)?/g

    /**
     * Scan a string value for violations and report each one.
     * @param {string} value - The className string
     * @param {import('estree').Node} node - The AST node to report on
     */
    function checkString(value, node) {
      let match
      // Reset lastIndex for global regex
      PATTERN.lastIndex = 0
      while ((match = PATTERN.exec(value)) !== null) {
        context.report({
          node,
          messageId: 'redundantDarkOverride',
          data: { token: match[0] },
        })
      }
    }

    return {
      JSXAttribute(node) {
        // Only check className (and class for completeness)
        if (node.name.name !== 'className' && node.name.name !== 'class') return

        const { value } = node
        if (!value) return

        // className="literal string"
        if (value.type === 'Literal' && typeof value.value === 'string') {
          checkString(value.value, node)
          return
        }

        // className={`template literal ${expr}`}
        if (value.type === 'JSXExpressionContainer') {
          const expr = value.expression

          // Direct template literal: className={`...`}
          if (expr.type === 'TemplateLiteral') {
            for (const quasi of expr.quasis) {
              if (quasi.value && quasi.value.raw) {
                checkString(quasi.value.raw, node)
              }
            }
            return
          }

          // Ternary: condition ? 'classA' : 'classB'
          if (expr.type === 'ConditionalExpression') {
            if (expr.consequent.type === 'Literal' && typeof expr.consequent.value === 'string') {
              checkString(expr.consequent.value, node)
            }
            if (expr.alternate.type === 'Literal' && typeof expr.alternate.value === 'string') {
              checkString(expr.alternate.value, node)
            }
            // Nested ternaries / template literals inside ternaries
            if (expr.consequent.type === 'TemplateLiteral') {
              for (const quasi of expr.consequent.quasis) {
                if (quasi.value && quasi.value.raw) checkString(quasi.value.raw, node)
              }
            }
            if (expr.alternate.type === 'TemplateLiteral') {
              for (const quasi of expr.alternate.quasis) {
                if (quasi.value && quasi.value.raw) checkString(quasi.value.raw, node)
              }
            }
            return
          }

          // Logical: condition && 'classA'
          if (expr.type === 'LogicalExpression') {
            if (expr.right.type === 'Literal' && typeof expr.right.value === 'string') {
              checkString(expr.right.value, node)
            }
            if (expr.left.type === 'Literal' && typeof expr.left.value === 'string') {
              checkString(expr.left.value, node)
            }
            return
          }

          // String literal wrapped in expression: className={'literal'}
          if (expr.type === 'Literal' && typeof expr.value === 'string') {
            checkString(expr.value, node)
          }
        }
      },

      // Also catch object-style className: className={{ 'dark:text-danger-400': true }}
      // This is less common but worth catching.
      // Note: JSXAttribute value for object is JSXExpressionContainer > ObjectExpression
    }
  },
}
