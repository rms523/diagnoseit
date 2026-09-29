module.exports = function (api) {
  api.cache(true);
  return {
    // babel-preset-expo already enables the automatic JSX runtime and, when
    // react-native-worklets is installed, injects its Babel plugin (Reanimated 4).
    // Do not also add react-native-reanimated/plugin or jsx-self/source plugins.
    presets: ['babel-preset-expo'],
  };
};
