const swaggerJsdoc = require('swagger-jsdoc');

const swaggerSpec = swaggerJsdoc({
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'Gateway API',
      version: '1.0.0',
      description: 'Sandbox sample REST API gateway',
    },
    components: {
      securitySchemes: {
        bearerAuth: {
          type: 'http',
          scheme: 'bearer',
          bearerFormat: 'JWT',
        },
      },
      schemas: {
        User: {
          type: 'object',
          properties: {
            id: { type: 'string', format: 'uuid' },
            username: { type: 'string' },
            dob: { type: 'string', format: 'date' },
            role: { type: 'string', enum: ['founder', 'investor'] },
            profileId: { type: 'string', format: 'uuid', nullable: true },
            createdAt: { type: 'string', format: 'date-time' },
            updatedAt: { type: 'string', format: 'date-time' },
          },
        },
        Profile: {
          type: 'object',
          properties: {
            id: { type: 'string', format: 'uuid' },
            company_name: { type: 'string' },
            country: { type: 'string', nullable: true },
            stage: { type: 'string', nullable: true },
            num_of_employees: { type: 'integer', nullable: true },
            industry: { type: 'string', nullable: true },
            target_region: { type: 'string', nullable: true },
            arr: { type: 'number', nullable: true },
            where_you_operate: { type: 'string', nullable: true },
            website: { type: 'array', items: { type: 'string' }, nullable: true },
            description_product: { type: 'string', nullable: true },
            checks: { type: 'string', nullable: true },
            createdAt: { type: 'string', format: 'date-time' },
            updatedAt: { type: 'string', format: 'date-time' },
          },
        },
        ProfileInput: {
          type: 'object',
          properties: {
            company_name: { type: 'string' },
            country: { type: 'string' },
            stage: { type: 'string' },
            num_of_employees: { type: 'integer' },
            industry: { type: 'string' },
            target_region: { type: 'string' },
            arr: { type: 'number' },
            where_you_operate: { type: 'string' },
            website: { type: 'array', items: { type: 'string' } },
            description_product: { type: 'string' },
            checks: { type: 'string' },
          },
        },
        Error: {
          type: 'object',
          properties: {
            error: { type: 'string' },
          },
        },
      },
    },
    security: [{ bearerAuth: [] }],
  },
  apis: ['./src/routes/*.js'],
});

module.exports = swaggerSpec;
