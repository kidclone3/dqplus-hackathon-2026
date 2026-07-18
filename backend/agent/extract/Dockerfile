# extract-agent :3003 — builds extracted_profiles rows + embeddings (Express).
# Runs schema.sql (CREATE EXTENSION vector, extracted_profiles) at startup.
FROM node:22-slim

WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 3003
CMD ["node", "src/index.js"]
