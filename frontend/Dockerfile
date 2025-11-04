FROM node:18-alpine

WORKDIR /usr/src/app
COPY package.json package-lock.json* ./
RUN npm install || true
COPY . .
EXPOSE 3000
ENV NEXT_PUBLIC_API_BASE=http://api:8000
CMD ["npm", "run", "dev"]
