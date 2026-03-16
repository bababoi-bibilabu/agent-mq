FROM node:22-slim

WORKDIR /app
COPY mcp/package.json mcp/package-lock.json ./
RUN npm ci
COPY mcp/tsconfig.json ./
COPY mcp/src/ ./src/
RUN npx tsc

ENTRYPOINT ["node", "dist/index.js"]
