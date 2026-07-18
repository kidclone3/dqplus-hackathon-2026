const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');

const Profile = sequelize.define(
  'Profile',
  {
    id: {
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true,
    },
    company_name: {
      type: DataTypes.STRING,
      allowNull: false,
    },
    country: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    stage: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    num_of_employees: {
      type: DataTypes.INTEGER,
      allowNull: true,
    },
    industry: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    target_region: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    arr: {
      type: DataTypes.DECIMAL(18, 2),
      allowNull: true,
    },
    where_you_operate: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    website: {
      type: DataTypes.ARRAY(DataTypes.STRING),
      allowNull: true,
      defaultValue: [],
    },
    description_product: {
      type: DataTypes.STRING,
      allowNull: true,
    },
    checks: {
      type: DataTypes.STRING,
      allowNull: true,
    },
  },
  {
    tableName: 'profiles',
    underscored: true,
    timestamps: true,
  }
);

module.exports = Profile;
