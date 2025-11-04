// jest.config.js
// Configuration file for Jest

module.exports = {
  // Set the test environment to jsdom (browser simulation)
  testEnvironment: 'jsdom',
  
  // Where to find the test files
  testMatch: [
    '**/tests/**/*.test.js',
    '**/__tests__/**/*.js',
    '**/?(*.)+(spec|test).js'
  ],
  
  // Code coverage - only collect from src directory
  collectCoverageFrom: [
    'src/**/*.js',
    '!**/node_modules/**',
    '!**/tests/**',
    '!**/htmlcov/**',
    '!jest.config.js'
  ],
  
  // Ignore certain files and directories
  testPathIgnorePatterns: [
    '/node_modules/',
    '/htmlcov/'
  ],
  
  // Coverage thresholds
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80
    }
  },
  
  // Additional settings
  verbose: true,
  
  // Clear mocks between tests
  clearMocks: true,
  
  // Coverage directory
  coverageDirectory: 'coverage',
  
  // Coverage reporters
  coverageReporters: ['text', 'lcov', 'html']
};