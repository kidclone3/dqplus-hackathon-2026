# matching-engine :3002 — pgvector cosine + attribute scoring (Express).
FROM node:22-slim

WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 3002
CMD ["node", "src/index.js"]
