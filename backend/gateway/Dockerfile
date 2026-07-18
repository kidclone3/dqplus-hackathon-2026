# gateway :3000 — auth + profiles (Express/Sequelize). node:22-slim (glibc) so
# bcrypt's prebuilt native binary is used instead of compiling from source.
FROM node:22-slim

WORKDIR /app
# NODE_ENV deliberately NOT set to production: src/index.js only runs
# sequelize.sync({ alter: true }) — the app's sole schema mechanism — outside production.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 3000
CMD ["node", "src/index.js"]
