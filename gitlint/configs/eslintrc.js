module.exports = {
  env: {
    browser: true,
    es6: true,
    node: true
  },
  extends: [
    'react-app',
    'airbnb',
    'plugin:prettier/recommended',
    'prettier/react'
  ],
  rules: {
    'prettier/prettier': 'error',
    camelcase: 1,
    quotes: [
      'error',
      'single',
      { avoidEscape: true, allowTemplateLiterals: true }
    ],
    globals: {
      jest: 'off',
      describe: 'off',
      it: 'off'
    },
    semi: ['error', 'never'],
    'linebreak-style': ['error', 'unix'],
    'func-names': 0,
    'no-underscore-dangle': 1,
    'no-use-before-define': 1,
    'no-unused-expressions': [2, { allowShortCircuit: true }],
    'import/no-named-as-default': 0,
    'import/prefer-default-export': 0,
    'import/no-extraneous-dependencies': [
      1,
      {
        devDependencies: ['.storybook/**', '**/*.stories.js', '**/*.test.js']
      }
    ],
    'react/jsx-filename-extension': 0,
    'react/prop-types': 1,
    'react/no-multi-comp': 0,
    'react/jsx-one-expression-per-line': 0,
    'react/destructuring-assignment': 1,
    'react/forbid-prop-types': [true, { forbid: ['any'] }],
    'react/require-default-props': 1,
    'react/default-props-match-prop-types': 1,
    'jsx-a11y/no-static-element-interactions': 0,
    'jsx-a11y/click-events-have-key-events': 0,
    'jsx-a11y/anchor-has-content': 0,
    'class-methods-use-this': 0,
    'consistent-return': 1
  }
}