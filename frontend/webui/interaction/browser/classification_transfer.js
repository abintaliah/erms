/* Browser acceptance checks for the disposable preview owned by
 * tools/test_scheme_transfer.py --preview. Run with a CUA tab after signing in
 * as the disposable transfer user. The adapter uses only documented CUA
 * Playwright methods; no HTTP, database, application-state, or storage bypass.
 * Run one phase at a time to retain inspection/progress between UI actions.
 */
function classificationTransferChecks(tab) {
    const page = tab.playwright;
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const clean = text => text.replace(/[\uFE00-\uFE0F\u2063\u2064]/g, '');
    const snapshot = async () => clean(await page.domSnapshot());
    return {
        async paged() {
            await page.getByRole('combobox', {name:/Sort by/}).click();
            await page.getByRole('option', {name:/Creation order/}).click();
            await page.getByRole('button', {name:/Load more/}).click();
            await page.getByRole('button', {name:/Expand or collapse scheme/}).nth(49).waitFor({state:'visible'});
            assert(await page.getByRole('button', {name:/Expand or collapse scheme/}).count() === 50,
                'Expected two loaded pages');
            return 'PASS non-default sort and two pages prepared';
        },
        async retainedPages() {
            assert(await page.getByRole('button', {name:/Expand or collapse scheme/}).count() === 50,
                'Import lost loaded pages');
            assert(clean(await page.getByRole('combobox', {name:/Sort by/}).getAttribute('value')) === 'Creation order',
                'Import lost sort');
            return 'PASS sort and pagination retained';
        },
        async pending() {
            // Hold classification_schemes in SHARE mode on the disposable DB
            // before this phase; release it after navigation or identity change.
            await page.getByRole('dialog').getByRole('button', {name:/Import/}).dblclick();
            assert(!(await page.getByRole('dialog').getByRole('button', {name:/Import/}).isEnabled()),
                'Pending import permits duplicate submission');
            await page.getByRole('dialog').getByRole('button', {name:/Cancel/}).click();
            await page.getByRole('dialog').waitFor({state:'hidden'});
            return 'PASS pending submission disabled';
        },
        async abandoned() {
            const text = await snapshot();
            assert(!text.includes('Import classification scheme') && !text.includes('Classification tree'),
                'Abandoned import replaced the current page');
            return 'PASS abandoned completion leaves current page intact';
        },
        async viewer() {
            const text = await snapshot();
            assert(text.includes('viewer@test.invalid') && text.includes('No assigned roles'),
                'Expected separate viewer account menu');
            assert(!text.includes('button "Import"') && !text.includes('UI-IDENTITY'),
                'Previous identity result leaked');
            return 'PASS identity and transfer permissions isolated';
        },
        async list() {
            await page.getByRole('button', {name:'Classification schemes', exact:true}).click();
            await page.getByRole('textbox', {name:/Filter schemes/}).waitFor({state:'visible'});
            const text = await snapshot();
            assert(text.includes('button "Import"') && text.includes('button "Add scheme"'), 'Import must be beside Add on the list');
            await page.getByRole('textbox', {name:/Filter schemes/}).fill('UI-TRANSFER');
            await page.getByRole('textbox', {name:/Filter schemes/}).press('Enter');
            await page.getByText(/No matching schemes/).waitFor({state:'visible'});
            assert(await page.getByRole('button', {name:/Import/}).isEnabled(), 'Import must work on an empty result');
            return 'PASS list placement and empty filtered result';
        },
        async choose(path) {
            await page.getByRole('button', {name:/Import/}).click();
            const dialog = page.getByRole('dialog');
            await dialog.waitFor({state:'visible'});
            assert(!(await dialog.getByRole('button', {name:/Import/}).isEnabled()), 'Import requires a selected file');
            const pending = page.waitForEvent('filechooser', {timeoutMs:10000});
            await page.getByRole('button', {name:'Choose File',exact:true}).last().click();
            const chooser = await pending;
            await chooser.setFiles([path]);
            await dialog.getByText(/100.00%/).first().waitFor({state:'visible'});
            return 'PASS file upload';
        },
        async imported() {
            await page.getByRole('dialog').getByRole('button', {name:/Import/}).click();
            await page.getByRole('dialog').waitFor({state:'hidden'});
            await page.getByRole('button', {name:/UI-TRANSFER/}).waitFor({state:'visible'});
            const text = await snapshot();
            assert(text.includes('textbox "Filter schemes": UI-TRANSFER'), 'Import must preserve the filter');
            assert(text.includes('status: Draft'), 'Imported scheme must display Draft');
            assert(text.includes('button "Add scheme"'), 'Success must remain on the list');
            return 'PASS import, draft, filter preservation, freshness, and stay-on-list';
        },
        async duplicate() {
            await page.getByRole('dialog').getByRole('button', {name:/Import/}).click();
            await page.getByRole('dialog').getByText(/already exists/).waitFor({state:'visible'});
            assert((await snapshot()).includes('textbox "Filter schemes": UI-TRANSFER'), 'Failure must retain the page');
            await page.getByRole('dialog').getByRole('button', {name:/Cancel/}).click();
            await page.getByRole('dialog').waitFor({state:'hidden'});
            return 'PASS duplicate rejection and failure retention';
        },
        async details() {
            await page.getByRole('button', {name:/UI-TRANSFER/}).click();
            await page.getByRole('button', {name:/Export/}).waitFor({state:'visible'});
            assert(!(await snapshot()).includes('button "Import"'), 'Import must not appear on details');
            await page.getByRole('button', {name:/Export/}).click();
            await page.getByText('MS Word', {exact:true}).waitFor({state:'visible'});
            const text = await snapshot();
            assert(text.includes('generic: JSON') && text.includes('generic: CSV'), 'All export formats must appear');
            await page.getByText('MS Word', {exact:true}).click();
            await page.getByRole('combobox', {name:/Document language/}).waitFor({state:'visible'});
            await page.getByRole('combobox', {name:/Document language/}).click();
            for (const language of ['English','العربية','Français'])
                assert(await page.getByRole('option', {name:language,exact:true}).isVisible(), 'Missing language '+language);
            return 'PASS details placement, formats, and registry-driven language options';
        },
        async geometry(direction) {
            const result = await page.evaluate(() => {
                const dialog = document.querySelector('[role="dialog"]');
                const card = dialog?.querySelector('.classification-transfer-dialog');
                const native = card?.querySelector('.q-field__native');
                const label = card?.querySelector('.q-field__label');
                return {direction:card && getComputedStyle(card).direction,
                    width:card?.getBoundingClientRect().width, viewport:innerWidth,
                    nativeFlow:native && getComputedStyle(native).flexDirection,
                    labelLeft:label && getComputedStyle(label).left,
                    labelRight:label && getComputedStyle(label).right};
            });
            assert(result.direction === direction, 'Wrong dialog direction');
            assert(result.width <= result.viewport, 'Dialog exceeds viewport');
            if (direction === 'rtl') {
                assert(result.nativeFlow === 'row', 'RTL field reversed twice');
                assert(result.labelLeft !== '0px' && result.labelRight === '0px', 'RTL label on wrong edge');
            }
            return {status:'PASS dialog direction and geometry', ...result};
        },
    };
}
