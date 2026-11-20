FROM node:20-alpine
WORKDIR /app
COPY dashboard/package.json ./package.json
RUN npm install
COPY dashboard ./
ENV BACKEND_URL=http://backend:8000
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
