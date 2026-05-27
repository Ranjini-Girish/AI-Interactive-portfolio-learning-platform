FROM node:18-slim
WORKDIR /app
COPY package.json package-lock.json* ./
COPY . .
RUN npm install --no-progress --no-audit --no-fund
CMD ["npm", "test"]
