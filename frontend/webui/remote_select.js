// Shared server-filtered NiceGUI Select. QSelect still owns focus, keyboard
// navigation, chips and selection; only the redundant label filter is omitted.
export default {
  props: ["options"],
  template: `
    <q-select ref="qRef" :options="options" @filter="filter"
      @popup-show="opened" @popup-hide="closed">
      <template v-for="(_, slot) in $slots" v-slot:[slot]="slotProps">
        <slot :name="slot" v-bind="slotProps || {}" />
      </template>
    </q-select>`,
  methods: {
    filter(value, update) { update(); },
    opened() { document.documentElement.classList.add("nicegui-select-popup-open"); },
    async closed() {
      await this.$nextTick();
      document.documentElement.classList.remove("nicegui-select-popup-open");
    },
  },
  unmounted() { this.closed(); },
};
